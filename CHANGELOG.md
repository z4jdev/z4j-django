# Changelog

All notable changes to `z4j-django` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-04-28

### Changed

- **v1.1.0 ecosystem family bump.** Pinned ``z4j-core>=1.1.0`` and ``z4j-bare>=1.1.0`` so a Django host installed at 1.1.0 always resolves a known-good 1.1.0 slice of brain + agent. The driving fix lives in z4j-bare 1.1.0: the agent dispatcher now correctly routes ``schedule.fire`` to the queue engine's ``submit_task``, instead of rejecting every brain-side scheduler tick with ``"unrecognized schedule action 'schedule.fire'"`` or ``"no scheduler adapter registered for None"``. Operators running brain 1.1.0 + scheduler 1.1.0 with z4j-django 1.0.x had every scheduled task silently fail at the agent - this floor refuses that mixed install.

## [1.0.6] - 2026-04-24

### Added

- **`python manage.py z4j_doctor`** - end-to-end agent connectivity check. Runs the same probes the agent runtime would (buffer dir writable, brain DNS, TCP, TLS, WebSocket upgrade), but synchronously and without starting the persistent agent. Output is human-readable text by default or JSON with `--json` for scripts. `--no-websocket` skips the network round-trip when the brain is intentionally offline. Exits 0 on all-green, 1 if any probe failed.
  - Diagnoses the gunicorn-under-`www-data` startup failure (buffer dir not writable) without having to grep service logs.
  - Diagnoses NAT / firewall / TLS-cert / wrong-token / wrong-project_id situations with a specific failure reason instead of a vague "agent shows unknown in dashboard".
  - Reports auto-detected engines so operators can confirm the celery app is being found from the web process (and the dashboard's Engines column will populate).

### Changed

- Bumped minimum `z4j-core` to `>=1.0.4` (for `BufferStorageError`) and `z4j-bare` to `>=1.0.6` (for the smart buffer-path fallback and the reusable `z4j_bare.diagnostics` probes the doctor command wraps). Picks up the silent-startup-failure fix automatically: gunicorn under `www-data` now relocates the buffer to `$TMPDIR/z4j-{uid}/buffer-{pid}.sqlite` instead of crashing on `mkdir /var/www/.z4j`.

## [1.0.1] - 2026-04-21

### Changed

- Lowered minimum Python version from 3.13 to 3.11. This package now supports Python 3.11, 3.12, 3.13, and 3.14.
- Documentation polish: standardized on ASCII hyphens across README, CHANGELOG, and docstrings for consistent rendering on PyPI.


## [1.0.0] - 2026-04

### Added

<!--
TODO: describe what ships in this first public release. One bullet per
capability. Examples:
- First public release.
- <Headline feature>
- <Second feature>
- N unit tests.
-->

- First public release.

## Links

- Repository: <https://github.com/z4jdev/z4j-django>
- Issues: <https://github.com/z4jdev/z4j-django/issues>
- PyPI: <https://pypi.org/project/z4j-django/>

[Unreleased]: https://github.com/z4jdev/z4j-django/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/z4jdev/z4j-django/releases/tag/v1.0.0
