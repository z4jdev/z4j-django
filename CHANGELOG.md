# Changelog

## 1.8.0 (2026-07-23)

* The Django integration now installs the agent under `celery beat` (the scheduler previously showed as unknown), and celery-flag subcommand parsing handles value-taking flags.
* Part of the coordinated 1.8.0 fleet release (unified fleet version, green lint/format/import-boundary gate).

## 1.7.0 (2026-07-07)

* The agent no longer auto-starts under `manage.py z4j*` management commands, so the z4j CLI runs without a competing runtime.
* Python 3.11 is now the minimum supported version (3.10 dropped).
* Part of the coordinated 1.7.0 fleet release (unified fleet version, green lint/format/import-boundary gate).

## 1.4.0 (2026-05-02)

Initial 1.4.0 release: Django adapter. Add `z4j_django` to `INSTALLED_APPS` and the agent starts when Django boots.
