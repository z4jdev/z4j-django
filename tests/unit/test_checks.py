"""Tests for ``z4j_django.checks``."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.core.checks import Error, Warning

from z4j_django.checks import check_z4j_settings


class TestCheckRequired:
    def test_no_z4j_setting_is_an_error(self) -> None:
        # The autouse fixture removed Z4J already.
        issues = check_z4j_settings()
        assert any(isinstance(i, Error) for i in issues)
        assert any(i.id == "z4j.E001" for i in issues)

    def test_non_dict_is_an_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "Z4J", "not-a-dict", raising=False)
        issues = check_z4j_settings()
        assert any(i.id == "z4j.E001" for i in issues)

    def test_missing_required_keys_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "Z4J", {"brain_url": "https://x"}, raising=False)
        issues = check_z4j_settings()
        assert any(i.id == "z4j.E002" for i in issues)


class TestBrainUrl:
    def test_invalid_brain_url(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            settings,
            "Z4J",
            {
                "brain_url": "not-a-url",
                "token": "z4j_agent_test_" + "a" * 44,
                "project_id": "test",
            },
            raising=False,
        )
        issues = check_z4j_settings()
        assert any(i.id == "z4j.E003" for i in issues)

    def test_http_warning_for_non_localhost(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            settings,
            "Z4J",
            {
                "brain_url": "http://z4j.example.com",
                "token": "z4j_agent_test_" + "a" * 44,
                "project_id": "test",
            },
            raising=False,
        )
        issues = check_z4j_settings()
        assert any(
            isinstance(i, Warning) and i.id == "z4j.W002" for i in issues
        )

    def test_http_localhost_no_warning(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            settings,
            "Z4J",
            {
                "brain_url": "http://localhost:7700",
                "token": "z4j_agent_test_" + "a" * 44,
                "project_id": "test",
            },
            raising=False,
        )
        issues = check_z4j_settings()
        assert not any(i.id == "z4j.W002" for i in issues)


class TestProjectId:
    def test_invalid_project_id(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            settings,
            "Z4J",
            {
                "brain_url": "https://z4j.example.com",
                "token": "z4j_agent_test_" + "a" * 44,
                "project_id": "INVALID_UPPERCASE",
            },
            raising=False,
        )
        issues = check_z4j_settings()
        assert any(i.id == "z4j.E004" for i in issues)


class TestPlaceholderToken:
    def test_placeholder_warning(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            settings,
            "Z4J",
            {
                "brain_url": "https://z4j.example.com",
                "token": "changeme-please-replace",
                "project_id": "test",
            },
            raising=False,
        )
        issues = check_z4j_settings()
        assert any(i.id == "z4j.W001" for i in issues)


class TestMiddlewareWarning:
    def test_middleware_missing_warning(
        self,
        z4j_settings: dict,
    ) -> None:
        issues = check_z4j_settings()
        assert any(i.id == "z4j.W003" for i in issues)

    def test_middleware_present_no_warning(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            settings,
            "MIDDLEWARE",
            ["z4j_django.context.Z4JContextMiddleware"],
        )
        issues = check_z4j_settings()
        assert not any(i.id == "z4j.W003" for i in issues)


class TestEnvVarFallback:
    def test_env_satisfies_required_check(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("Z4J_BRAIN_URL", "https://z4j.example.com")
        monkeypatch.setenv("Z4J_TOKEN", "z4j_agent_envtest_" + "a" * 44)
        monkeypatch.setenv("Z4J_PROJECT_ID", "env-project")
        # No settings.Z4J at all - env vars should be enough.
        # But we still need settings.Z4J to be set to something
        # because the first check rejects None outright.
        monkeypatch.setattr(settings, "Z4J", {}, raising=False)
        issues = check_z4j_settings()
        assert not any(i.id == "z4j.E002" for i in issues)
