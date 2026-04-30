"""``python manage.py z4j_reconcile`` - declarative scheduler reconcile (1.2.2+).

Reads ``Z4J_SCHEDULES`` (and optionally ``CELERY_BEAT_SCHEDULE`` if
``Z4J_RECONCILE_CELERY_BEAT=True``) from Django settings, translates
to z4j schedule rows, and POSTs to the brain's ``:import`` endpoint
with ``mode=replace_for_source``.

Usage:

    python manage.py z4j_reconcile              # apply
    python manage.py z4j_reconcile --dry-run    # preview only
    python manage.py z4j_reconcile --json       # machine-readable

Exit codes:

    0  - success (or no-op when Z4J_SCHEDULES is empty)
    1  - the brain rejected the import (HTTP error or validation)
    2  - missing required Django settings (brain_url, token, etc.)
"""

from __future__ import annotations

import json
import sys
from typing import Any

from django.conf import settings as django_settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Reconcile Z4J_SCHEDULES (+ optional CELERY_BEAT_SCHEDULE) "
        "against the brain. mode=replace_for_source so absent "
        "schedules are removed."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "Preview the diff (insert/update/delete counts) without "
                "writing audit rows. Useful for CI deploy gates."
            ),
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON instead of text.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from z4j_django.declarative import reconcile_from_django_settings

        result = reconcile_from_django_settings(
            django_settings, dry_run=options["dry_run"],
        )

        if result is None:
            msg = (
                "z4j_reconcile: no schedules configured. "
                "Set Z4J_SCHEDULES or Z4J_RECONCILE_CELERY_BEAT=True."
            )
            if options["json"]:
                self.stdout.write(
                    json.dumps({"ok": True, "skipped": True, "reason": msg}),
                )
            else:
                self.stdout.write(msg)
            sys.exit(0)

        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "ok": result.failed == 0,
                        "dry_run": result.dry_run,
                        "inserted": result.inserted,
                        "updated": result.updated,
                        "unchanged": result.unchanged,
                        "failed": result.failed,
                        "deleted": result.deleted,
                        "errors": result.errors,
                    },
                ),
            )
        else:
            mode = "DRY-RUN " if result.dry_run else ""
            self.stdout.write(f"z4j_reconcile {mode}summary:")
            self.stdout.write(f"  inserted:  {result.inserted}")
            self.stdout.write(f"  updated:   {result.updated}")
            self.stdout.write(f"  unchanged: {result.unchanged}")
            self.stdout.write(f"  deleted:   {result.deleted}")
            if result.failed:
                self.stdout.write(self.style.ERROR(
                    f"  failed:    {result.failed}",
                ))
                for idx, err in result.errors.items():
                    self.stdout.write(self.style.ERROR(f"    [{idx}] {err}"))
            else:
                self.stdout.write(self.style.SUCCESS("  failed:    0"))

        sys.exit(1 if result.failed else 0)
