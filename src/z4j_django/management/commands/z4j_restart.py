"""``python manage.py z4j_restart`` - force the agent to reconnect now.

Sends ``SIGHUP`` to the running Django agent (looked up via the
pidfile under ``$Z4J_RUNTIME_DIR``). The supervisor drops its
current connection and reconnects immediately, skipping the
remaining backoff timer.

Use this after operator-driven events when waiting for the
exponential backoff is unacceptable:

- Agent token rotation
- Brain restart
- TLS cert rotation
- DNS change

Returns exit 0 on success, 1 on operator-fixable failure (no
pidfile, stale PID), 2 on platform issue (Windows: not yet
supported - restart your host process via your supervisor).
"""

from __future__ import annotations

import sys
from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Force the running Django z4j agent to drop its current "
        "connection and reconnect immediately (SIGHUP via pidfile)."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        from z4j_bare.control import send_restart

        rc, msg = send_restart("django")
        if rc == 0:
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            self.stderr.write(self.style.ERROR(f"z4j-django restart: {msg}"))
        sys.exit(rc)
