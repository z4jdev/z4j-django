# z4j-django

[![PyPI version](https://img.shields.io/pypi/v/z4j-django.svg)](https://pypi.org/project/z4j-django/)
[![Python](https://img.shields.io/pypi/pyversions/z4j-django.svg)](https://pypi.org/project/z4j-django/)
[![License](https://img.shields.io/pypi/l/z4j-django.svg)](https://github.com/z4jdev/z4j-django/blob/main/LICENSE)

The Django framework adapter for [z4j](https://z4j.com).

Adds the z4j agent into your Django project as a single
`INSTALLED_APPS` entry. Auto-discovers the engine adapter you have
installed (Celery, RQ, Dramatiq, Huey, arq, TaskIQ) and streams every
task lifecycle event from your Django workers to z4j. Operator
control actions (retry, cancel, bulk retry, purge, restart) flow back
the same channel.

## What it ships

- **One-line install**, add `"z4j_django"` to `INSTALLED_APPS`; the
  agent starts when Django boots, no decorator on every task
- **Engine auto-discovery**, picks up whichever z4j engine adapter
  is installed alongside (Celery, RQ, Dramatiq, Huey, arq, TaskIQ).
  Multiple engines in the same project are first-class.
- **Schedule integration**, pair with `z4j-celerybeat` to surface
  django-celery-beat schedules on the dashboard's Schedules page
- **`@z4j_meta` decorator**, optional per-task annotations
  (`priority="critical"`, `description="..."`) that the dashboard
  honors for filtering and SLO display
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

The agent reads its bearer token from `Z4J_AGENT_TOKEN`, z4j URL
from `Z4J_BRAIN_URL`, and the project slug from `Z4J_PROJECT`. Mint
the token from the dashboard's Agents page.

## Reliability

- No exception from the agent ever propagates back into Django request
  handlers, signals, or your worker code.
- Events buffer locally when z4j is unreachable; your application
  never blocks on network I/O.
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
