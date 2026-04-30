"""Django settings shim for the declarative scheduler reconciler (1.2.2+).

The reconciler logic lives in ``z4j_bare.declarative`` so all
framework adapters share it. This module is the Django-specific
glue: it reads ``Z4J_SCHEDULES`` (and optional
``CELERY_BEAT_SCHEDULE`` if ``Z4J_RECONCILE_CELERY_BEAT=True``)
from Django settings and runs one reconcile pass.

Settings the operator can supply:

- ``Z4J_SCHEDULES``: dict of ``{name: {task, kind, expression, ...}}``
  in z4j-native shape (matches ``ScheduleCreateIn`` minus the
  deployment-specific fields).
- ``Z4J_RECONCILE_CELERY_BEAT`` (default ``False``): also read
  ``CELERY_BEAT_SCHEDULE`` and add the translated specs.
- ``Z4J_SCHEDULE_DEFAULT_ENGINE`` (default ``"celery"``): which
  engine all reconciled schedules target.
- ``Z4J_SCHEDULE_OWNER`` (optional): override the project's
  ``default_scheduler_owner`` for THIS reconciler's writes.
- ``Z4J_RECONCILE_SOURCE_TAG`` (default ``"declarative:django"``):
  the ``source`` label written on each reconciled schedule. Must
  be a value in the brain's
  ``_REPLACE_FOR_SOURCE_ALLOWLIST`` (the colon-prefix form is
  the canonical declarative-source vocabulary). Used by
  ``mode=replace_for_source`` so the reconciler only deletes
  schedules it owns.

The reconciler is invoked:

- Manually via ``python manage.py z4j_reconcile [--dry-run]``.
- Optionally automatically from ``apps.py:Z4JDjangoConfig.ready()``
  if ``Z4J_RECONCILE_AUTORUN=True``. Auto-run is OFF by default
  because reconciling on every Django process boot (gunicorn
  fan-out, runserver autoreload) writes audit rows N times. The
  right pattern for production is reconcile from a deploy hook
  OR from CI.
"""

from __future__ import annotations

import logging
from typing import Any

# Re-export the shared types for backward compatibility with any
# integration code that imported from z4j_django (1.2.2 alpha)
# before the refactor.
from z4j_bare.declarative import (
    ReconcileResult,
    ScheduleReconciler,
    _spec_to_brain_payload,
    _z4j_native_schedules_to_specs,
)

logger = logging.getLogger("z4j.agent.django.reconcile")


def reconcile_from_django_settings(
    settings: Any,
    *,
    dry_run: bool = False,
) -> ReconcileResult | None:
    """Read Django settings and run one reconcile pass.

    Returns ``None`` when no schedules are configured (silent no-op
    so we don't spam logs from a host that doesn't use the feature).

    Required settings:
    - ``Z4J["brain_url"]`` and ``Z4J["project_id"]``
    - ``Z4J["token"]`` (project API key with ADMIN scope; needed
      for :import).

    Optional settings (defaults shown):
    - ``Z4J_SCHEDULES = {}``
    - ``Z4J_RECONCILE_CELERY_BEAT = False``
    - ``Z4J_SCHEDULE_DEFAULT_ENGINE = "celery"``
    - ``Z4J_SCHEDULE_OWNER = None``  # falls back to project default
    - ``Z4J_RECONCILE_SOURCE_TAG = "declarative:django"``
    """
    z4j_schedules = getattr(settings, "Z4J_SCHEDULES", None) or {}
    reconcile_celery = getattr(settings, "Z4J_RECONCILE_CELERY_BEAT", False)
    celery_beat_schedules = (
        getattr(settings, "CELERY_BEAT_SCHEDULE", None) or {}
        if reconcile_celery
        else None
    )

    if not z4j_schedules and not celery_beat_schedules:
        return None

    z4j_settings = getattr(settings, "Z4J", None) or {}
    brain_url = z4j_settings.get("brain_url")
    api_key = z4j_settings.get("token")
    project_slug = z4j_settings.get("project_id")
    if not (brain_url and api_key and project_slug):
        logger.warning(
            "z4j-django reconcile: Z4J_SCHEDULES configured but "
            "Z4J['brain_url'], Z4J['token'], or Z4J['project_id'] "
            "missing; skipping reconcile.",
        )
        return None

    engine = getattr(settings, "Z4J_SCHEDULE_DEFAULT_ENGINE", "celery")
    scheduler = getattr(settings, "Z4J_SCHEDULE_OWNER", None)
    source = getattr(
        settings, "Z4J_RECONCILE_SOURCE_TAG", "declarative:django",
    )

    reconciler = ScheduleReconciler(
        brain_url=brain_url,
        api_key=api_key,
        project_slug=project_slug,
    )
    return reconciler.reconcile(
        z4j_schedules=z4j_schedules,
        celery_beat_schedules=celery_beat_schedules,
        engine=engine,
        scheduler=scheduler,
        source=source,
        dry_run=dry_run,
    )


__all__ = [
    "ReconcileResult",
    "ScheduleReconciler",
    "_spec_to_brain_payload",
    "_z4j_native_schedules_to_specs",
    "reconcile_from_django_settings",
]
