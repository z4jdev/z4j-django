"""Shared fixtures for z4j-django unit tests.

Configures a minimal Django settings module BEFORE any z4j_django
import happens, so the package's lazy ``django.conf.settings``
imports work in test isolation.
"""

from __future__ import annotations

import os

import django
import pytest
from django.conf import settings


def _configure_django() -> None:
    """Set up Django with the minimum settings z4j_django needs.

    Idempotent: ``settings.configured`` is checked first.
    """
    if settings.configured:
        return
    settings.configure(
        DEBUG=True,
        DATABASES={
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": ":memory:",
            },
        },
        INSTALLED_APPS=[
            "django.contrib.contenttypes",
            "django.contrib.auth",
            "z4j_django",
        ],
        MIDDLEWARE=[],
        ROOT_URLCONF="tests.unit.urls_stub",
        USE_TZ=True,
        SECRET_KEY="z4j-test-secret-not-real",
    )
    django.setup()


_configure_django()


@pytest.fixture(autouse=True)
def _clear_z4j_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset Z4J-related settings + env vars between tests.

    Most tests configure their own Z4J dict per-test; this fixture
    ensures we don't carry state across tests.
    """
    if hasattr(settings, "Z4J"):
        delattr(settings._wrapped, "Z4J")  # type: ignore[attr-defined]
    for key in [
        "Z4J_BRAIN_URL",
        "Z4J_TOKEN",
        "Z4J_PROJECT_ID",
        "Z4J_ENVIRONMENT",
        "Z4J_DEV_MODE",
        "Z4J_STRICT_MODE",
        "Z4J_AUTOSTART",
        "Z4J_DISABLED",
    ]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def z4j_settings(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Helper fixture: returns a default Z4J settings dict and applies it."""
    payload = {
        "brain_url": "https://z4j.example.com",
        "token": "z4j_agent_test_" + "a" * 44,
        "project_id": "test-project",
    }
    monkeypatch.setattr(settings, "Z4J", payload, raising=False)
    return payload
