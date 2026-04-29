"""The :class:`DjangoFrameworkAdapter`.

Implements :class:`z4j_core.protocols.FrameworkAdapter` for Django.
The adapter is constructed inside :meth:`apps.Z4JDjangoConfig.ready`,
which calls :func:`z4j_django.config.build_config_from_django` to
load configuration first, then hands the resulting Config to the
adapter and the agent runtime.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from z4j_core.models import Config, DiscoveryHints, RequestContext, User

from z4j_django.context import current_request_context, current_user
from z4j_django.discovery import collect_django_hints


class DjangoFrameworkAdapter:
    """Framework adapter for Django.

    Implements the :class:`FrameworkAdapter` Protocol via duck typing
    (no inheritance - see ``docs/patterns.md §2``). Lifecycle hooks
    are stored as plain lists; :meth:`fire_startup` and
    :meth:`fire_shutdown` invoke them when called by the agent
    runtime.

    Attributes:
        name: Always ``"django"``.
        _config: The resolved :class:`Config` for this Django process.
    """

    name: str = "django"

    #: Worker-first protocol (1.2.0+) role hint. Django agents
    #: embedded in gunicorn / uvicorn / daphne processes default
    #: to "web" because that's where 95% of Django installations
    #: load this adapter from. Operators running Django as a Celery
    #: worker (rare but legitimate) override via Z4J_WORKER_ROLE.
    default_worker_role: str = "web"

    def __init__(self, config: Config) -> None:
        self._config = config
        self._startup_hooks: list[Callable[[], None]] = []
        self._shutdown_hooks: list[Callable[[], None]] = []

    # ------------------------------------------------------------------
    # FrameworkAdapter Protocol
    # ------------------------------------------------------------------

    def discover_config(self) -> Config:
        return self._config

    def discovery_hints(self) -> DiscoveryHints:
        return collect_django_hints()

    def current_context(self) -> RequestContext | None:
        return current_request_context()

    def current_user(self) -> User | None:
        return current_user()

    def on_startup(self, hook: Callable[[], None]) -> None:
        self._startup_hooks.append(hook)

    def on_shutdown(self, hook: Callable[[], None]) -> None:
        self._shutdown_hooks.append(hook)

    def register_admin_view(self, view: Any) -> None:  # noqa: ARG002
        # Phase 1: no-op. The optional Django admin embed lands in
        # Phase 1.1 alongside the dashboard polish.
        return None

    # ------------------------------------------------------------------
    # Internal helpers used by AppConfig.ready
    # ------------------------------------------------------------------

    def fire_startup(self) -> None:
        """Invoke every registered startup hook in order.

        Called once after the agent runtime has connected. Exceptions
        from individual hooks are caught and logged so a single bad
        hook does not abort the others.
        """
        import logging

        logger = logging.getLogger("z4j.agent.django.framework")
        for hook in self._startup_hooks:
            try:
                hook()
            except Exception:  # noqa: BLE001
                logger.exception("z4j django startup hook failed")

    def fire_shutdown(self) -> None:
        """Invoke every registered shutdown hook in order.

        Called once during process shutdown. Same exception
        semantics as :meth:`fire_startup`.
        """
        import logging

        logger = logging.getLogger("z4j.agent.django.framework")
        for hook in self._shutdown_hooks:
            try:
                hook()
            except Exception:  # noqa: BLE001
                logger.exception("z4j django shutdown hook failed")


__all__ = ["DjangoFrameworkAdapter"]
