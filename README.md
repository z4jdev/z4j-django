# z4j-django

[![PyPI version](https://img.shields.io/pypi/v/z4j-django.svg)](https://pypi.org/project/z4j-django/)
[![Python](https://img.shields.io/pypi/pyversions/z4j-django.svg)](https://pypi.org/project/z4j-django/)
[![License](https://img.shields.io/pypi/l/z4j-django.svg)](https://github.com/z4jdev/z4j-django/blob/main/LICENSE)

The Django framework adapter for [z4j](https://z4j.com).

Adds the z4j agent to a Django process as a single `INSTALLED_APPS`
entry. The Django integration locates a configured Celery app when
`z4j-celery` is installed, and `z4j-celery` separately bootstraps the agent in
Celery worker processes. Installing an RQ, Dramatiq, Huey, arq, or TaskIQ
adapter does not by itself activate that engine in Django; wire those worker
processes through the engine-specific or framework-free integration.

## Compatibility

- Django 5.2.17 or newer (below Django 6) on Python 3.11
- Django 6.0.8 or newer with no adapter cap on Python 3.12+
- Python 3.11+

A standalone Python 3.12+ install can resolve Django 6.1. The Celery and
all-extras lanes currently resolve Django 6.0.8 because
`django-celery-beat` still declares `Django<6.1`; that is an upstream
coexistence constraint, not a stale security pin.

Pair with an engine adapter (`z4j-celery`, `z4j-rq`, `z4j-dramatiq`, `z4j-huey`, `z4j-arq`, `z4j-taskiq`); each engine adapter carries its own upstream floor.

Full per-adapter matrix at <https://z4j.dev/reference/compatibility/>.

## What it ships

- **One-line install**, add `"z4j_django"` to `INSTALLED_APPS`; the
  agent starts when Django boots, no decorator on every task
- **Celery discovery and worker bootstrap**, locates the configured Celery app
  in Django processes and registers a separate engine-aware runtime inside
  Celery workers
- **Schedule integration**, pair with `z4j-celerybeat` to surface
  django-celery-beat schedules on the dashboard's Schedules page
- **Per-task metadata from supporting engine adapters**; `z4j-celery`,
  `z4j-rq`, and `z4j-dramatiq` expose `@z4j_meta` rather than this framework
  package defining one
- **Service-user safe**, auto-relocates the local outbound buffer
  to `$TMPDIR/z4j-{uid}` when `$HOME` is unwritable (gunicorn
  under `www-data`, `nginx`, etc.)

## Install

```bash
pip install z4j-django z4j-celery z4j-celerybeat
```

Then in `settings.py`:

```python
INSTALLED_APPS = [
    # ...
    "django_celery_beat",  # if you use celery-beat
    "z4j_django",
]
```

The agent reads its bearer token from `Z4J_TOKEN`, mandatory envelope-signing
secret from `Z4J_HMAC_SECRET`, z4j URL from `Z4J_BRAIN_URL`, and project id from
`Z4J_PROJECT_ID`. The Agents page shows the token and HMAC secret when the
agent is minted; retain both values.

## Reliability

- Agent startup and delivery failures are logged and isolated from Django
  request handlers, signals, and worker code; capture hooks make no brain
  network request inline.
- Engine event queues and the SQLite outbound buffer are bounded. Queue
  overflow drops new events and buffer pressure evicts oldest rows; both losses
  are logged.
- Agent reconnects on every transient failure with bounded backoff.

## Documentation

Full docs at [z4j.dev/frameworks/django/](https://z4j.dev/frameworks/django/).

## License

Apache-2.0, see [LICENSE](LICENSE).

## Links

- Homepage: https://z4j.com
- Documentation: https://z4j.dev
- PyPI: https://pypi.org/project/z4j-django/
- Issues: https://github.com/z4jdev/z4j-django/issues
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Security: security@z4j.com (see [SECURITY.md](SECURITY.md))
