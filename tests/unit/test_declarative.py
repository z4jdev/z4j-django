"""Tests for the Django declarative reconciler (1.2.2+).

Covers:

- Translating ``Z4J_SCHEDULES`` (z4j-native shape) to ScheduleSpec
- Mixing ``Z4J_SCHEDULES`` with ``CELERY_BEAT_SCHEDULE`` (native wins)
- Building the brain ``:import`` request body with the right
  ``mode`` and ``source_filter``
- The brain HTTP call (mocked via httpx ``MockTransport``)
- The ``reconcile_from_django_settings`` settings-reading shim
"""

from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest

from z4j_django.declarative import (
    ReconcileResult,
    ScheduleReconciler,
    _spec_to_brain_payload,
    _z4j_native_schedules_to_specs,
    reconcile_from_django_settings,
)
from z4j_core.celerybeat_compat import ScheduleSpec


# ---------------------------------------------------------------------------
# Native schedule translator
# ---------------------------------------------------------------------------


class TestNativeTranslator:
    def test_full_native_entry(self) -> None:
        specs = _z4j_native_schedules_to_specs({
            "send-daily": {
                "task": "myapp.tasks.send_digest",
                "kind": "cron",
                "expression": "0 9 * * *",
                "args": [1],
                "kwargs": {"x": "y"},
                "queue": "default",
            },
        })
        assert len(specs) == 1
        s = specs[0]
        assert s.name == "send-daily"
        assert s.task_name == "myapp.tasks.send_digest"
        assert s.kind == "cron"
        assert s.expression == "0 9 * * *"
        assert s.args == [1]
        assert s.kwargs == {"x": "y"}
        assert s.queue == "default"

    def test_minimal_entry(self) -> None:
        specs = _z4j_native_schedules_to_specs({
            "tick": {
                "task": "myapp.tasks.tick",
                "kind": "interval",
                "expression": "30",
            },
        })
        assert len(specs) == 1
        assert specs[0].args == []
        assert specs[0].kwargs == {}
        assert specs[0].queue is None
        assert specs[0].timezone == "UTC"

    def test_missing_task_skipped(self) -> None:
        specs = _z4j_native_schedules_to_specs({
            "broken": {"kind": "cron", "expression": "0 9 * * *"},
        })
        assert specs == []

    def test_missing_kind_or_expression_skipped(self) -> None:
        specs = _z4j_native_schedules_to_specs({
            "no-kind": {"task": "x", "expression": "0 9 * * *"},
            "no-expr": {"task": "y", "kind": "cron"},
        })
        assert specs == []


# ---------------------------------------------------------------------------
# Reconciler request body
# ---------------------------------------------------------------------------


class TestRequestBody:
    def test_spec_to_payload_includes_source_hash(self) -> None:
        spec = ScheduleSpec(
            name="x",
            task_name="myapp.tasks.x",
            kind="cron",
            expression="0 9 * * *",
        )
        payload = _spec_to_brain_payload(
            spec,
            engine="celery",
            scheduler="z4j-scheduler",
            source="declarative:django",
        )
        # source_hash is deterministic for the same content
        assert "source_hash" in payload
        assert len(payload["source_hash"]) == 64
        # The brain-shaped fields are populated
        assert payload["name"] == "x"
        assert payload["engine"] == "celery"
        assert payload["scheduler"] == "z4j-scheduler"
        assert payload["source"] == "declarative:django"

    def test_scheduler_omitted_when_none(self) -> None:
        """scheduler=None means brain falls back to project default."""
        spec = ScheduleSpec(
            name="x",
            task_name="myapp.tasks.x",
            kind="cron",
            expression="0 9 * * *",
        )
        payload = _spec_to_brain_payload(
            spec, engine="celery", scheduler=None, source="t",
        )
        assert "scheduler" not in payload

    def test_replace_for_source_mode(self) -> None:
        reconciler = ScheduleReconciler(
            brain_url="http://b",
            api_key="k",
            project_slug="proj",
        )
        body = reconciler._build_request_body(
            [
                ScheduleSpec(
                    name="x",
                    task_name="t",
                    kind="cron",
                    expression="0 9 * * *",
                ),
            ],
            engine="celery",
            scheduler="z4j-scheduler",
            source="declarative:django",
        )
        assert body["mode"] == "replace_for_source"
        assert body["source_filter"] == "declarative:django"
        assert len(body["schedules"]) == 1


# ---------------------------------------------------------------------------
# HTTP integration (mocked transport)
# ---------------------------------------------------------------------------


class TestHttpFlow:
    def test_import_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["body"] = json.loads(request.content)
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(
                200,
                json={
                    "inserted": 1,
                    "updated": 0,
                    "unchanged": 0,
                    "failed": 0,
                    "deleted": 0,
                    "errors": {},
                },
            )

        # Patch httpx.Client with our mock transport
        original_client = ScheduleReconciler._http_client

        def patched(self) -> httpx.Client:
            return httpx.Client(
                base_url=self.brain_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                transport=httpx.MockTransport(handler),
            )

        monkeypatch.setattr(ScheduleReconciler, "_http_client", patched)

        reconciler = ScheduleReconciler(
            brain_url="http://b", api_key="my-key", project_slug="myproj",
        )
        result = reconciler.reconcile(
            z4j_schedules={
                "x": {
                    "task": "myapp.tasks.x",
                    "kind": "cron",
                    "expression": "0 9 * * *",
                },
            },
        )
        assert result.inserted == 1
        assert result.failed == 0
        assert "/projects/myproj/schedules:import" in captured["url"]
        assert captured["auth"] == "Bearer my-key"
        assert captured["body"]["mode"] == "replace_for_source"

    def test_dry_run_calls_diff(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(
                200,
                json={"insert": 2, "update": 1, "unchanged": 5, "delete": 0},
            )

        def patched(self) -> httpx.Client:
            return httpx.Client(
                base_url=self.brain_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                transport=httpx.MockTransport(handler),
            )

        monkeypatch.setattr(ScheduleReconciler, "_http_client", patched)

        reconciler = ScheduleReconciler(
            brain_url="http://b", api_key="k", project_slug="proj",
        )
        result = reconciler.reconcile(
            z4j_schedules={
                "x": {
                    "task": "t",
                    "kind": "interval",
                    "expression": "60",
                },
            },
            dry_run=True,
        )
        assert result.dry_run is True
        assert result.inserted == 2
        assert result.updated == 1
        assert result.unchanged == 5
        assert "/schedules:diff" in captured["url"]


# ---------------------------------------------------------------------------
# Mix Z4J_SCHEDULES + CELERY_BEAT_SCHEDULE
# ---------------------------------------------------------------------------


class TestMixedSources:
    def test_native_wins_on_name_conflict(self) -> None:
        reconciler = ScheduleReconciler(
            brain_url="http://b", api_key="k", project_slug="proj",
        )
        specs = reconciler.collect_specs(
            z4j_schedules={
                "shared": {
                    "task": "from-native",
                    "kind": "cron",
                    "expression": "0 9 * * *",
                },
            },
            celery_beat_schedules={
                "shared": {
                    "task": "from-celery",
                    "schedule": dt.timedelta(seconds=30),
                },
            },
        )
        assert len(specs) == 1
        assert specs[0].task_name == "from-native"

    def test_both_sources_distinct_names(self) -> None:
        reconciler = ScheduleReconciler(
            brain_url="http://b", api_key="k", project_slug="proj",
        )
        specs = reconciler.collect_specs(
            z4j_schedules={
                "native-only": {
                    "task": "myapp.t1",
                    "kind": "interval",
                    "expression": "60",
                },
            },
            celery_beat_schedules={
                "celery-only": {
                    "task": "myapp.t2",
                    "schedule": dt.timedelta(seconds=30),
                },
            },
        )
        assert {s.name for s in specs} == {"native-only", "celery-only"}


# ---------------------------------------------------------------------------
# Settings-reading shim
# ---------------------------------------------------------------------------


class _FakeSettings:
    """Stand-in for Django settings module."""

    def __init__(self, **kwargs: object) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestSettingsShim:
    def test_no_schedules_returns_none(self) -> None:
        settings = _FakeSettings(
            Z4J={"brain_url": "http://b", "token": "k", "project_id": "proj"},
        )
        result = reconcile_from_django_settings(settings)
        assert result is None

    def test_missing_brain_url_returns_none(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        settings = _FakeSettings(
            Z4J_SCHEDULES={
                "x": {"task": "t", "kind": "cron", "expression": "0 9 * * *"},
            },
            Z4J={},  # missing brain_url, token, project_id
        )
        result = reconcile_from_django_settings(settings)
        assert result is None
        # warning was logged
        assert any("missing" in r.message for r in caplog.records)

    def test_celery_beat_only_via_flag(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "inserted": 1,
                    "updated": 0,
                    "unchanged": 0,
                    "failed": 0,
                    "deleted": 0,
                    "errors": {},
                },
            )

        def patched(self) -> httpx.Client:
            return httpx.Client(
                base_url=self.brain_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                transport=httpx.MockTransport(handler),
            )

        monkeypatch.setattr(ScheduleReconciler, "_http_client", patched)

        settings = _FakeSettings(
            Z4J={"brain_url": "http://b", "token": "k", "project_id": "proj"},
            Z4J_RECONCILE_CELERY_BEAT=True,
            CELERY_BEAT_SCHEDULE={
                "every-min": {
                    "task": "myapp.tasks.tick",
                    "schedule": 60,
                },
            },
        )
        result = reconcile_from_django_settings(settings)
        assert result is not None
        assert result.inserted == 1
        assert len(captured["body"]["schedules"]) == 1
        assert captured["body"]["schedules"][0]["expression"] == "60"
