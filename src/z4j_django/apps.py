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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.apps import AppConfig

from z4j_bare._process_singleton import clear_runtime, try_register
from z4j_bare.runtime import AgentRuntime

from z4j_django.framework import DjangoFrameworkAdapter

if TYPE_CHECKING:
    from z4j_core.protocols import QueueEngineAdapter, SchedulerAdapter

logger = logging.getLogger("z4j.agent.django.apps")

# Eagerly import z4j_celery (if installed) at module-load time so its
# ``celery.signals.worker_init`` handler is connected before any
# Celery worker process tries to fire it. Without this, when the user
# runs ``celery -A myproj worker``, the only z4j entry point loaded is
# z4j-django (via INSTALLED_APPS) - and our ``ready()`` SKIPS startup
# under a celery invocation so z4j-celery owns the worker. But that
# split breaks if z4j-celery's signal handler was never connected:
# nobody starts the runtime, no tasks reach the brain. Importing the
# package here triggers its ``__init__.py`` which calls
# ``register_worker_bootstrap()`` exactly once. The signal never fires
# in non-worker contexts (web/runserver), so this is cheap.
try:
    import z4j_celery  # noqa: F401  - imported for the import side-effect
except ImportError:
    # z4j-celery is optional. The user simply isn't using Celery.
    pass

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

        # Skip in the Django autoreload PARENT process. ``runserver``
        # spawns two processes: the parent watches files and respawns
        # the child on change; the child is the one actually serving.
        # Both call ``ready()``, so without this guard both would open
        # WebSockets to the brain - the brain treats the second as a
        # "newer connection" and force-closes the first with code 4002.
        # The result was noisy startup logs ("connection closed during
        # send: received 4002") even though everything was fine.
        # Django marks the child with RUN_MAIN=true.
        if _is_autoreload_parent():
            logger.debug("z4j: skipping startup in autoreload parent process")
            return

        # Skip when running under ``celery worker`` / ``celery beat``.
        # In a Celery worker process the project's settings get loaded
        # too (Django gets bootstrapped by the user's celery.py) so our
        # ``ready()`` fires - but the right install path for a worker
        # is ``z4j_celery.worker_bootstrap`` which attaches the Celery
        # engine adapter to the runtime. If we start the runtime here
        # (without the engine), we win the singleton race; the celery
        # worker_init signal then sees an engine-less runtime and the
        # worker captures no task events. Letting z4j-celery own the
        # worker process (and z4j-django own the web/runserver process)
        # keeps responsibility clean.
        if _is_celery_invocation():
            logger.debug(
                "z4j: skipping startup under celery; "
                "z4j-celery worker_bootstrap will install the agent",
            )
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


def _is_celery_invocation() -> bool:
    """Return True if the process is being launched as a Celery sub-command.

    Recognises the common shapes - ``celery -A app worker``,
    ``python -m celery worker``, ``uv run celery worker``, etc. We
    skip starting the agent from z4j-django when a Celery sub-command
    is in flight so :mod:`z4j_celery.worker_bootstrap` can own the
    install (with the Celery engine adapter attached). Without this
    check, the engine-less runtime z4j-django would build wins the
    process singleton and z4j-celery's signal handler hands back the
    same engine-less runtime, so worker task events go un-captured.
    """
    import sys

    argv = sys.argv or []
    if not argv:
        return False
    prog = os.path.basename(argv[0]).lower()
    if prog in {"celery", "celery.exe"}:
        return True
    # ``python -m celery ...`` and ``uv run celery ...`` and friends.
    # Cheap and correct: scan the first few tokens for a literal
    # ``celery`` / ``celery.exe``.
    for tok in argv[1:6]:
        if os.path.basename(tok).lower() in {"celery", "celery.exe"}:
            return True
    return False


def _is_autoreload_parent() -> bool:
    """Return True if we're the Django autoreload parent (watcher) process.

    ``runserver`` (and other autoreloading commands) spawn a child
    process to actually run the app, and the child has the env var
    ``RUN_MAIN=true`` set by Django. The parent does not - the parent
    just watches files and respawns the child. We want the agent to
    run in the child, not the parent, so the brain sees one connection
    per host instead of two-fighting-each-other.
    """
    import sys

    # Only relevant when an autoreloading command was invoked.
    autoreload_commands = {"runserver", "runserver_plus"}
    if not sys.argv or len(sys.argv) < 2 or sys.argv[1] not in autoreload_commands:
        return False
    # The user can pass ``--noreload``; in that case there is only one
    # process and RUN_MAIN is unset, but the agent should run.
    if "--noreload" in sys.argv:
        return False
    # The child process has RUN_MAIN=true. If we don't see it, we are
    # the parent watcher - skip.
    return os.environ.get("RUN_MAIN", "").lower() != "true"


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
        # INFO not WARNING: in the standard split-process layout the
        # web/runserver agent has nothing to capture (no worker runs
        # here) and the celery worker process owns its own agent
        # via ``z4j_celery.worker_bootstrap``. An empty engine list
        # in the web process is normal and benign.
        logger.info(
            "z4j: no queue engine adapters available in this process. "
            "If you run Celery / RQ / Dramatiq workers, install the "
            "matching adapter (e.g. ``pip install z4j-celery``) and "
            "they will register themselves in the worker process.",
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
        # INFO not WARNING: this is non-fatal in the most common
        # case. The web process (runserver/gunicorn/uvicorn) usually
        # only enqueues tasks via ``task.delay()`` - the Celery
        # WORKER process is what actually executes them and emits
        # task lifecycle events. The worker process gets its own
        # agent runtime via ``z4j_celery.worker_bootstrap`` (signal
        # handler on ``celery.signals.worker_init``) which builds
        # the engine itself - so dashboard task tracking works fine
        # even when this auto-detect comes up empty in the web
        # process. The only side-effect of an empty result here is
        # that ``task.delay()`` calls from web code are not
        # captured as "task sent" events.
        logger.info(
            "z4j: no Celery app located in this process; "
            "task lifecycle will still be captured by the celery "
            "worker. To also capture task-sent events from web "
            'code, add CELERY_APP = "<your_project>.celery:app" '
            "to settings.py.",
        )
        return None
    return CeleryEngineAdapter(celery_app=celery_app)


def _resolve_celery_app() -> Any:
    """Locate the Celery app via several common conventions.

    Resolution order (first hit wins):

    1. ``settings.CELERY_APP`` - explicit override (object or dotted
       ``"module:attr"``/``"module.attr"`` string). Always honored.
    2. ``celery.current_app`` - if any code in this process has already
       constructed a Celery app (e.g. ``from .celery import app`` at
       project import time, which is the cookiecutter-django pattern),
       Celery's own current-app machinery returns it without us having
       to guess the module path.
    3. Module-path guesses, in order: ``<ROOT_URLCONF>.celery.app``,
       ``<WSGI_APPLICATION>.celery.app``, ``<ASGI_APPLICATION>.celery.app``,
       ``<BASE_DIR.name>.celery.app``. These cover Django, ASGI, and
       cookiecutter conventions where the celery module sits next to
       ``settings.py``.

    Returns ``None`` if no app can be found, but distinguishes
    *missing* from *broken*: an ImportError on a guessed
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

    # Module-path guesses. The cookiecutter convention puts ``celery.py``
    # alongside ``settings.py`` inside the project package; we walk
    # several Django settings that name that package.
    candidates: list[str] = []

    def _add(module_name: str | None) -> None:
        if not module_name:
            return
        head = module_name.split(".", 1)[0]
        if head and head not in candidates:
            candidates.append(head)

    _add(getattr(settings, "ROOT_URLCONF", None))
    _add(getattr(settings, "WSGI_APPLICATION", None))
    _add(getattr(settings, "ASGI_APPLICATION", None))
    base_dir = getattr(settings, "BASE_DIR", None)
    if base_dir is not None:
        try:
            _add(Path(str(base_dir)).name)
        except Exception:  # noqa: BLE001
            pass

    import importlib

    # Pass 1: project-package attribute lookup. The cookiecutter
    # convention is ``<project>/__init__.py`` doing ``from .celery
    # import app as celery_app`` so the app is reachable as
    # ``<project>.celery_app`` (and sometimes as ``app``). This
    # works EVEN if the user's ``celery.py`` lives somewhere
    # non-standard, as long as ``__init__.py`` re-exports it.
    for root_module_name in candidates:
        try:
            pkg = importlib.import_module(root_module_name)
        except ImportError:
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "z4j: %s package imported but raised %s: %s",
                root_module_name,
                type(exc).__name__,
                exc,
            )
            continue
        for attr_name in ("celery_app", "app"):
            app = getattr(pkg, attr_name, None)
            if app is not None and _looks_like_celery_app(app):
                return app

    # Pass 2: Celery's current-app machinery. If anything in this
    # process imported and configured a Celery app, this returns it.
    # We do this AFTER pass 1 because the package import in pass 1
    # is what triggers the user's ``celery.py`` to load (and become
    # current) in the first place.
    try:
        from celery import current_app  # type: ignore[import-not-found]
        active = current_app._get_current_object()  # noqa: SLF001
    except Exception:  # noqa: BLE001
        active = None
    if active is not None and _looks_like_celery_app(active):
        return active

    # Pass 3: explicit module-path guesses. Falls back to looking
    # for ``<project>.celery.app`` for users whose __init__.py does
    # NOT re-export the app.
    for root_module_name in candidates:
        try:
            celery_module = importlib.import_module(f"{root_module_name}.celery")
        except ImportError:
            continue
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "z4j: %s.celery imported but raised %s: %s",
                root_module_name,
                type(exc).__name__,
                exc,
            )
            return None
        app = getattr(celery_module, "app", None)
        if app is not None:
            return app

    return None


def _looks_like_celery_app(obj: Any) -> bool:
    """Return True if ``obj`` looks like a configured Celery app.

    Excludes the un-configured default app (whose ``main`` is
    ``"default"`` or empty) so a stray ``import celery`` somewhere
    in the project does not poison auto-detect with a useless app.
    """
    main = getattr(obj, "main", None)
    if main in (None, "", "default", "__main__"):
        return False
    # Duck-typing: a real Celery app has ``send_task`` and ``tasks``.
    return hasattr(obj, "send_task") and hasattr(obj, "tasks")


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
