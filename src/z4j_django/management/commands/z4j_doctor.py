"""``python manage.py z4j_doctor`` - end-to-end agent connectivity check.

Runs the same probes the agent runtime would, but synchronously and
without starting the persistent agent. Lets operators diagnose:

- Buffer dir not writable (the gunicorn-under-www-data class of bug)
- Brain DNS / TCP / TLS issues (NAT, firewall, cert mismatch)
- WebSocket upgrade rejected (token wrong, project_id wrong, HMAC missing)
- Celery / scheduler adapters loadable but no app discovered

Output is plain text by default, or JSON with ``--json`` for scripts.
Always exits with code 0 unless a probe failed - then 1.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Run agent connectivity diagnostics: buffer path, DNS, TCP, "
        "TLS, WebSocket upgrade, and engine auto-detection."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit machine-readable JSON instead of human-readable text.",
        )
        parser.add_argument(
            "--no-websocket",
            action="store_true",
            help=(
                "Skip the WebSocket upgrade probe. Useful when the brain "
                "is intentionally offline and you only want to verify "
                "local config + buffer path."
            ),
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from z4j_bare import diagnostics

        from z4j_django.config import build_config_from_django

        try:
            config = build_config_from_django()
        except Exception as exc:  # noqa: BLE001
            self._emit_config_failure(exc, options)
            sys.exit(1)

        results = []
        results.append(diagnostics.probe_buffer_path(config.buffer_path))
        if not results[-1].ok:
            self._emit_results(results, config, options)
            sys.exit(1)

        brain_url = str(config.brain_url)
        for probe in (
            diagnostics.probe_dns,
            diagnostics.probe_tcp,
            diagnostics.probe_tls,
        ):
            results.append(probe(brain_url))
            if not results[-1].ok:
                self._emit_results(results, config, options)
                sys.exit(1)

        if not options["no_websocket"]:
            results.append(diagnostics.probe_websocket(config))

        # Engine auto-detect (informational - never fails the run).
        engines = self._detect_engines()

        self._emit_results(results, config, options, engines=engines)
        sys.exit(0 if all(r.ok for r in results) else 1)

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _emit_config_failure(self, exc: Exception, options: dict[str, Any]) -> None:
        if options["json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "ok": False,
                        "stage": "config",
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    indent=2,
                ),
            )
            return
        self.stderr.write(
            self.style.ERROR(
                f"FAIL: could not build config from Django settings: "
                f"{type(exc).__name__}: {exc}",
            ),
        )

    def _emit_results(
        self,
        results: list[Any],
        config: Any,
        options: dict[str, Any],
        engines: list[str] | None = None,
    ) -> None:
        if options["json"]:
            payload = {
                "ok": all(r.ok for r in results),
                "config": {
                    "brain_url": str(config.brain_url),
                    "project_id": config.project_id,
                    "agent_name": config.agent_name,
                    "buffer_path": str(config.buffer_path),
                    "transport": config.transport,
                    "dev_mode": config.dev_mode,
                },
                "engines": engines or [],
                "probes": [
                    {
                        "name": r.name,
                        "ok": r.ok,
                        "message": r.message,
                        "details": r.details,
                    }
                    for r in results
                ],
            }
            self.stdout.write(json.dumps(payload, indent=2))
            return

        self.stdout.write("z4j-doctor (django)")
        self.stdout.write("===================")
        self.stdout.write(f"  brain_url:   {config.brain_url}")
        self.stdout.write(f"  project_id:  {config.project_id}")
        self.stdout.write(f"  agent_name:  {config.agent_name or '<unset>'}")
        self.stdout.write(f"  buffer_path: {config.buffer_path}")
        self.stdout.write(f"  transport:   {config.transport}")
        self.stdout.write("")
        for r in results:
            tag = self.style.SUCCESS("[OK]  ") if r.ok else self.style.ERROR("[FAIL]")
            self.stdout.write(f"  {tag} {r.name:12s} {r.message}")
        if engines is not None:
            self.stdout.write("")
            self.stdout.write(f"  engines auto-detected: {', '.join(engines) or '<none>'}")
            if not engines:
                self.stdout.write(
                    "    (this is normal for a web process; engines register "
                    "from their own worker process via z4j-celery / z4j-rq)",
                )

    # ------------------------------------------------------------------
    # Engine detection (Django-specific)
    # ------------------------------------------------------------------

    def _detect_engines(self) -> list[str]:
        """Same auto-detect logic the runtime uses, surfaced for the doctor.

        Returns the list of engine *names* that would be installed in
        this process. Does NOT actually instantiate the engines or
        connect them to anything - this is a pure probe.
        """
        from z4j_django.apps import _discover_engines  # noqa: SLF001

        try:
            engines = _discover_engines()
        except Exception:  # noqa: BLE001
            return []
        return [e.name for e in engines]
