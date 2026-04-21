"""Django signal hooks for z4j_django.

Currently empty in v1: the only Django-specific signals we wire up
are ``post_save`` / ``post_delete`` on
``django_celery_beat.models.PeriodicTask``, but those live in
``z4j_celerybeat.signals`` because they belong to the scheduler
adapter, not the framework adapter.

This module exists as a stable namespace so future Django-specific
signal hooks (e.g. ``user_logged_in`` audit events, ``request_started``
context capture) have an obvious place to land.
"""

from __future__ import annotations


def connect_django_signals() -> None:
    """Hook into Django signals.

    No-op in v1. Future signals are wired here.
    """


def disconnect_django_signals() -> None:
    """Disconnect every signal handler this module installed.

    No-op in v1. Used by tests and shutdown.
    """


__all__ = ["connect_django_signals", "disconnect_django_signals"]
