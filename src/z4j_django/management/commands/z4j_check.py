"""``python manage.py z4j_check`` - compact pass/fail health check.

Mirrors ``z4j-django check`` (the standalone CLI form). Runs the
same probe ladder as ``z4j_doctor`` but emits one line per failed
probe (or a single OK line) - suitable for cron jobs, deploy
gates, and Nagios-style monitors.

Exit code is the standard pass/fail contract: 0 = healthy,
1 = at least one probe failed, 2 = config error.
"""

from __future__ import annotations

import sys
from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Compact pass/fail z4j agent health check. Same probes as "
        "z4j_doctor, exit 0/1 contract for scripts and monitors."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        from z4j_bare import diagnostics

        from z4j_django.config import build_config_from_django

        try:
            config = build_config_from_django()
        except Exception as exc:  # noqa: BLE001
            self.stderr.write(
                self.style.ERROR(
                    f"z4j-django check: config: FAIL "
                    f"({type(exc).__name__}: {exc})",
                ),
            )
            sys.exit(2)

        results = [diagnostics.probe_buffer_path(config.buffer_path)]
        for probe in (
            diagnostics.probe_dns,
            diagnostics.probe_tcp,
            diagnostics.probe_tls,
        ):
            r = probe(str(config.brain_url))
            results.append(r)
            if not r.ok:
                break

        fails = [r for r in results if not r.ok]
        if fails:
            for r in fails:
                self.stderr.write(
                    self.style.ERROR(
                        f"z4j-django check: {r.name}: FAIL ({r.message})",
                    ),
                )
            sys.exit(1)

        self.stdout.write(
            self.style.SUCCESS(
                f"z4j-django check: all green ({len(results)} probes)",
            ),
        )
        sys.exit(0)
