"""Django ``AppConfig`` for ``z4j_django``.

Hooks Z4J_DJANGO into Django's startup lifecycle. When Django boots
and ``z4j_django`` is in ``INSTALLED_APPS``, ``Z4JDjangoConfig.ready()``
is called once per process. We use that hook to:

1. Read the resolved configuration via :func:`config.build_config_from_django`
2. Construct the :class:`DjangoFrameworkAdapter`
3. Discover any installed engine adapters (``z4j-celery`` is the
   v1 default; absence is fine - it just means no engines run)
4. Discover any installed scheduler adapters (``z4j-celerybeat``)
5. Construct an :class:`AgentRuntime` and start it
6. Register an ``atexit`` shutdown hook so the runtime drains its
   buffer when the process exits cleanly

This entire flow is wrapped in a top-level try/except - if z4j
fails to start, Django keeps running. The host application is more
important than our observability tool.
"""

from __future__ import annotations

import atexit
import logging
import os
from typing import TYPE_CHECKING, Any

from django.apps import AppConfig

from z4j_bare._process_singleton import clear_runtime, try_register
from z4j_bare.runtime import AgentRuntime

from z4j_django.framework import DjangoFrameworkAdapter

if TYPE_CHECKING:
    from z4j_core.protocols import QueueEngineAdapter, SchedulerAdapter

logger = logging.getLogger("z4j.agent.django.apps")

# Module-level state - there is at most one runtime per Django process.
_runtime: AgentRuntime | None = None


class Z4JDjangoConfig(AppConfig):
    """Django app config for z4j_django.

    The ``ready()`` method runs once per worker process - under
    gunicorn that's once per worker; under runserver, once per
    autoreload restart.
    """

    name = "z4j_django"
    label = "z4j_django"
    verbose_name = "z4j Django integration"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """Bootstrap the agent runtime.

        Wrapped in a top-level try/except so a startup error in z4j
        cannot prevent Django from booting.
        """
        # Allow tests and tooling to disable the autostart entirely.
        if os.environ.get("Z4J_DISABLED", "").lower() in ("1", "true", "yes", "on"):
            logger.info("z4j: Z4J_DISABLED is set; skipping agent startup")
            return

        # Don't start the runtime during management commands that
        # are not actually running the app - ``manage.py migrate``,
        # ``collectstatic``, ``check``, etc. The agent should run
        # in worker / web processes, not one-shot scripts.
        if _is_management_command():
            logger.debug("z4j: skipping startup during management command")
            return

        global _runtime
        if _runtime is not None:
            return  # already started in this process

        try:
            candidate = _build_runtime()
        except Exception:  # noqa: BLE001
            logger.exception("z4j: failed to build agent runtime; continuing without it")
            _runtime = None
            return

        # Cooperate with ``z4j_celery.worker_bootstrap``: both paths
        # fire in a Django+Celery worker process, and the brain only
        # accepts ONE WebSocket per agent token at a time. The first
        # caller wins; the second gets the existing runtime back and
        # skips its own ``start()``.
        active = try_register(candidate, owner="z4j_django.apps")
        _runtime = active
        if active is not candidate:
            logger.info(
                "z4j: django app config reused an existing runtime; "
                "skipping start() (another install path won the race)",
            )
            return
        try:
            if candidate.config.autostart:
                candidate.start()
                candidate.framework.fire_startup()
        except Exception:  # noqa: BLE001
            logger.exception("z4j: failed to start agent runtime; continuing without it")
            # Release the slot so a later caller can try.
            clear_runtime()
            _runtime = None
            return

        atexit.register(_shutdown)
        logger.info("z4j: agent runtime started for django")

    @classmethod
    def get_runtime(cls) -> AgentRuntime | None:
        """Return the running agent runtime, if any.

        Used by tests and by management commands that want to flush
        the buffer manually.
        """
        return _runtime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_management_command() -> bool:
    """Return True if Django is running a one-shot management command.

    Heuristic: check ``sys.argv`` for the standard management
    commands that should NOT trigger an agent. We deliberately
    INclude ``runserver`` and ``runserver_plus`` (those run the app
    long-term and want the agent).
    """
    import sys

    if not sys.argv:
        return False

    skip_commands = {
        "migrate",
        "makemigrations",
        "collectstatic",
        "check",
        "showmigrations",
        "createsuperuser",
        "shell",
        "shell_plus",
        "test",
        "compilemessages",
        "makemessages",
        "dumpdata",
        "loaddata",
        "sqlmigrate",
        "diffsettings",
    }

    # ``manage.py <cmd>``: argv[1] is the command.
    if len(sys.argv) >= 2 and sys.argv[1] in skip_commands:
        return True

    return False


def _build_runtime() -> AgentRuntime:
    """Resolve config, discover adapters, construct the runtime.

    Does NOT call :meth:`AgentRuntime.start`. The caller must
    register with the process-wide singleton first (so a concurrent
    install path in the same process - typically
    ``celery.signals.worker_init`` under a Celery worker - cannot
    race us into opening two WebSocket sessions for the same agent
    token). The winner calls ``start()``; the loser drops its
    candidate.
    """
    from z4j_django.config import build_config_from_django

    config = build_config_from_django()
    framework = DjangoFrameworkAdapter(config)
    engines = _discover_engines()
    schedulers = _discover_schedulers()

    return AgentRuntime(
        config=config,
        framework=framework,
        engines=engines,
        schedulers=schedulers,
    )


def _discover_engines() -> list[QueueEngineAdapter]:
    """Try to import every supported engine adapter and instantiate it.

    v1 supports ``z4j_celery`` only. The list grows in v2.
    Failure to import an adapter (because it's not installed) is
    silent - the user simply gets the engines they pip-installed.
    """
    engines: list[QueueEngineAdapter] = []

    celery_engine = _try_import_celery_engine()
    if celery_engine is not None:
        engines.append(celery_engine)

    if not engines:
        logger.warning(
            "z4j: no queue engine adapters installed; the agent will run but "
            "will not capture any task events. pip install z4j-celery to fix.",
        )
    return engines


def _try_import_celery_engine() -> Any:
    """Best-effort import of CeleryEngineAdapter, wired to Django's Celery app.

    The convention in Django+Celery projects is that the Celery app
    is created in ``<project>/celery.py`` and exposed as ``app``. We
    look for that via ``django.conf.settings`` exposing ``CELERY_APP``,
    or fall back to ``app.celery_app`` per the cookiecutter-django
    convention.
    """
    try:
        from z4j_celery.engine import CeleryEngineAdapter
    except ImportError:
        return None

    celery_app = _resolve_celery_app()
    if celery_app is None:
        logger.warning(
            "z4j-celery is installed but no Celery app could be located; "
            "set settings.CELERY_APP to your celery.app instance.",
        )
        return None
    return CeleryEngineAdapter(celery_app=celery_app)


def _resolve_celery_app() -> Any:
    """Locate the Celery app via several common conventions.

    Returns ``None`` if no app can be found, but distinguishes
    *missing* from *broken*: an ImportError on the conventional
    ``<project>.celery`` module is silent, while *any other*
    exception inside that module is logged with the inner type and
    message - a broken celery.py is much more diagnostic-worthy than
    "you don't use Celery."
    """
    from django.conf import settings

    candidate = getattr(settings, "CELERY_APP", None)
    if candidate is not None:
        # CELERY_APP can be either:
        # - The actual Celery app object (e.g. ``from myapp.celery import app``)
        # - A dotted import path string (e.g. ``"myapp.celery:app"``)
        # Resolve strings to the real object.
        if isinstance(candidate, str):
            candidate = _resolve_import_path(candidate)
        if candidate is not None:
            return candidate

    # Try cookiecutter-django convention: <project>.celery has ``app``
    root_module_name = (
        getattr(settings, "ROOT_URLCONF", "").split(".", 1)[0] or ""
    )
    if not root_module_name:
        return None

    try:
        import importlib

        celery_module = importlib.import_module(f"{root_module_name}.celery")
    except ImportError:
        # No celery.py at all - user does not use Celery, totally fine.
        return None
    except Exception as exc:  # noqa: BLE001
        # User has a celery.py but it raised on import. Log the inner
        # type + message so the operator can see *what* broke without
        # having to dig through Django's startup output. Don't crash
        # - z4j stays optional.
        logger.warning(
            "z4j: %s.celery imported but raised %s: %s",
            root_module_name,
            type(exc).__name__,
            exc,
        )
        return None

    return getattr(celery_module, "app", None)


def _discover_schedulers() -> list[SchedulerAdapter]:
    """Try to import every supported scheduler adapter."""
    schedulers: list[SchedulerAdapter] = []

    beat = _try_import_celerybeat_scheduler()
    if beat is not None:
        schedulers.append(beat)

    return schedulers


def _try_import_celerybeat_scheduler() -> Any:
    try:
        from z4j_celerybeat.scheduler import CeleryBeatSchedulerAdapter
    except ImportError:
        return None
    # Pass the resolved Celery app so the scheduler can use it for
    # ``trigger_now`` (which calls ``celery_app.send_task``). Without
    # this, every "trigger now" command from the dashboard fails with
    # "Celery app not configured" - see CeleryBeatSchedulerAdapter
    # tests.
    celery_app = _resolve_celery_app()
    return CeleryBeatSchedulerAdapter(celery_app=celery_app)


def _resolve_import_path(path: str) -> Any:
    """Resolve ``"module.path:attribute"`` to the actual object.

    Supports two forms:
    - ``"myapp.celery:app"`` (colon-separated module + attribute)
    - ``"myapp.celery.app"`` (dot-separated, last segment is the attribute)
    """
    import importlib

    try:
        if ":" in path:
            module_path, attr_name = path.rsplit(":", 1)
        elif "." in path:
            module_path, attr_name = path.rsplit(".", 1)
        else:
            return None
        module = importlib.import_module(module_path)
        return getattr(module, attr_name, None)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "z4j: failed to resolve CELERY_APP=%r: %s: %s",
            path,
            type(exc).__name__,
            exc,
        )
        return None


def _shutdown() -> None:
    """``atexit`` handler that flushes the buffer and stops the runtime."""
    global _runtime
    if _runtime is None:
        return
    try:
        _runtime.stop(timeout=5.0)
    except Exception:  # noqa: BLE001
        logger.exception("z4j: error during shutdown")
    finally:
        _runtime = None
        clear_runtime()


__all__ = ["Z4JDjangoConfig"]
