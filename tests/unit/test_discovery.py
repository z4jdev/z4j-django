"""Tests for ``z4j_django.discovery.collect_django_hints``."""

from __future__ import annotations

from z4j_core.models import DiscoveryHints
from z4j_django.discovery import collect_django_hints


class TestCollectHints:
    def test_returns_discovery_hints_object(self) -> None:
        hints = collect_django_hints()
        assert isinstance(hints, DiscoveryHints)
        assert hints.framework_name == "django"

    def test_excludes_z4j_django_itself(self) -> None:
        hints = collect_django_hints()
        assert "z4j_django" not in hints.app_names

    def test_includes_django_contrib_apps(self) -> None:
        # The conftest installs django.contrib.{contenttypes,auth};
        # they should appear in the hints.
        hints = collect_django_hints()
        assert "django.contrib.contenttypes" in hints.app_names
        assert "django.contrib.auth" in hints.app_names

    def test_app_paths_are_directories(self) -> None:
        hints = collect_django_hints()
        for path in hints.app_paths:
            assert path.is_dir()
