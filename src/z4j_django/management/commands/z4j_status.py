"""``python manage.py z4j_status`` - one-line agent introspection.

Reads the pidfile registry under ``$Z4J_RUNTIME_DIR`` (default
``~/.z4j/``) and lists every running z4j agent on this host with
PID + liveness. Doesn't require a working brain - it's a pure
host-local introspection.

Exit 0 even if no agents are running (status is informational,
not pass/fail; use ``z4j_check`` for that).
"""

from __future__ import annotations

import os
import sys
from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "List every running z4j agent on this host (PID + liveness) "
        "by reading the pidfile registry. Host-local, no brain needed."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        from z4j_bare.control import _runtime_dir  # noqa: PLC0415

        rd = _runtime_dir()
        pidfiles = sorted(rd.glob("agent-*.pid"))
        if not pidfiles:
            self.stdout.write(
                f"z4j-django status: no running agents under {rd}",
            )
            sys.exit(0)

        self.stdout.write(f"z4j-django status: agents under {rd}")
        for pf in pidfiles:
            adapter = pf.stem.removeprefix("agent-")
            try:
                pid = int(pf.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                self.stdout.write(
                    f"  z4j-{adapter:12s}  pidfile unreadable: {pf}",
                )
                continue
            try:
                os.kill(pid, 0)
                alive = "running"
            except ProcessLookupError:
                alive = "stale (process not running)"
            except PermissionError:
                alive = "running (different user)"
            except OSError as exc:
                alive = f"unknown ({exc})"
            self.stdout.write(
                f"  z4j-{adapter:12s}  pid={pid}  {alive}",
            )
        sys.exit(0)
