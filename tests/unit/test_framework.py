"""Tests for ``z4j_django.framework.DjangoFrameworkAdapter``."""

from __future__ import annotations

from typing import Any

import pytest

from z4j_core.models import Config, DiscoveryHints
from z4j_core.protocols import FrameworkAdapter
from z4j_django.framework import DjangoFrameworkAdapter


@pytest.fixture
def adapter(z4j_settings: dict) -> DjangoFrameworkAdapter:
    config = Config(**z4j_settings)
    return DjangoFrameworkAdapter(config)


class TestProtocolConformance:
    def test_satisfies_framework_adapter_protocol(
        self, adapter: DjangoFrameworkAdapter,
    ) -> None:
        assert isinstance(adapter, FrameworkAdapter)

    def test_name_is_django(self, adapter: DjangoFrameworkAdapter) -> None:
        assert adapter.name == "django"


class TestConfigPassthrough:
    def test_discover_config_returns_constructed_config(
        self, adapter: DjangoFrameworkAdapter,
    ) -> None:
        config = adapter.discover_config()
        assert config.project_id == "test-project"


class TestDiscoveryHints:
    def test_returns_django_hints(
        self, adapter: DjangoFrameworkAdapter,
    ) -> None:
        hints = adapter.discovery_hints()
        assert isinstance(hints, DiscoveryHints)
        assert hints.framework_name == "django"


class TestContext:
    def test_no_request_returns_none(
        self, adapter: DjangoFrameworkAdapter,
    ) -> None:
        # No middleware → no request → None
        assert adapter.current_context() is None

    def test_no_user_returns_none(
        self, adapter: DjangoFrameworkAdapter,
    ) -> None:
        assert adapter.current_user() is None


class TestLifecycleHooks:
    def test_startup_hooks_fire_in_order(
        self, adapter: DjangoFrameworkAdapter,
    ) -> None:
        order: list[int] = []
        adapter.on_startup(lambda: order.append(1))
        adapter.on_startup(lambda: order.append(2))
        adapter.fire_startup()
        assert order == [1, 2]

    def test_shutdown_hooks_fire_in_order(
        self, adapter: DjangoFrameworkAdapter,
    ) -> None:
        order: list[int] = []
        adapter.on_shutdown(lambda: order.append(1))
        adapter.on_shutdown(lambda: order.append(2))
        adapter.fire_shutdown()
        assert order == [1, 2]

    def test_failing_hook_does_not_break_others(
        self, adapter: DjangoFrameworkAdapter,
    ) -> None:
        order: list[int] = []

        def boom() -> None:
            raise RuntimeError("nope")

        adapter.on_startup(boom)
        adapter.on_startup(lambda: order.append(1))
        adapter.fire_startup()
        assert order == [1]


class TestRegisterAdminView:
    def test_register_admin_view_is_noop(
        self, adapter: DjangoFrameworkAdapter,
    ) -> None:
        # Phase 1 - should be a no-op, never raise.
        sentinel: Any = object()
        adapter.register_admin_view(sentinel)
