# Changelog

## 1.11.0 (2026-09-10)

* Broaden the Django requirement to `django>=4.2`, with no Python marker and
  no adapter upper cap, and add the Django 4.2 classifier. This replaces the
  per-Python minimums `django>=5.2.17,<6` (Python 3.11) and `django>=6.0.8`
  (Python 3.12+) and drops the direct `sqlparse>=0.6.0` requirement, leaving
  SQLParse to Django's own metadata. Choose a Python and Django combination
  that Django itself supports.
* Removing those minimums is deliberate. They were security floors for
  Django's August 2026 security release and for SQLParse 0.6.0, but the
  adapter only uses the AppConfig, settings, system-check and management
  command APIs that Django 4.2, 5.2 and 6.x share, so its range now states API
  compatibility rather than an upstream patch policy. Installing or upgrading
  z4j-django no longer forces a Django or SQLParse upgrade, and no longer
  refuses a release those advisories affect. Keep the host on a supported,
  patched Django line: Django 4.2 support is legacy API compatibility, not a
  statement that 4.2 still receives upstream security fixes. See
  https://z4j.dev/reference/compatibility/.
* Align runtime version metadata and sibling dependency floors with the coordinated 1.11.0 release.

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
