# Changelog

## 1.10.0 (2026-08-28)

* Carried with the coordinated fleet release. No behaviour changed.

## 1.9.1 (2026-08-27)

* Carried with the coordinated fleet release. No adapter behaviour changed.

## 1.9.0 (2026-08-25)

* Raised the supported security floors to Django 5.2.17 on Python 3.11 and Django 6.0.8 on Python 3.12+, while keeping the Python 3.12+ adapter lane uncapped for standalone Django 6.1 installs.
* Declared SQLParse 0.6.0 as a direct security floor rather than relying on Django's transitive dependency.
* The Celery and all-extras lanes resolve Django 6.0.8 until `django-celery-beat` removes its upstream `Django<6.1` coexistence cap.

## 1.8.0 (2026-07-23)

* The Django integration now installs the agent under `celery beat` (the scheduler previously showed as unknown), and celery-flag subcommand parsing handles value-taking flags.
* Part of the coordinated 1.8.0 fleet release (unified fleet version, green lint/format/import-boundary gate).

## 1.7.0 (2026-07-07)

* The agent no longer auto-starts under `manage.py z4j*` management commands, so the z4j CLI runs without a competing runtime.
* Python 3.11 is now the minimum supported version (3.10 dropped).
* Part of the coordinated 1.7.0 fleet release (unified fleet version, green lint/format/import-boundary gate).

## 1.4.0 (2026-05-02)

Initial 1.4.0 release: Django adapter. Add `z4j_django` to `INSTALLED_APPS` and the agent starts when Django boots.
