# z4j-django

[![PyPI version](https://img.shields.io/pypi/v/z4j-django.svg)](https://pypi.org/project/z4j-django/)
[![Python](https://img.shields.io/pypi/pyversions/z4j-django.svg)](https://pypi.org/project/z4j-django/)
[![License](https://img.shields.io/pypi/l/z4j-django.svg)](https://github.com/z4jdev/z4j-django/blob/main/LICENSE)


**License:** Apache 2.0

Django framework adapter for [z4j](https://z4j.com). Drops into any
Django project via `INSTALLED_APPS` and bootstraps a z4j agent on
Django startup - no boilerplate, no signal wiring, no custom management
commands.

## Install

Pick your task engine and install with the matching extra. Each extra
pulls the engine adapter AND its companion scheduler in one shot, so
a fresh install never needs a second command.

```bash
pip install z4j-django[celery]      # Celery + celery-beat
pip install z4j-django[rq]          # RQ + rq-scheduler
pip install z4j-django[dramatiq]    # Dramatiq + APScheduler
pip install z4j-django[huey]        # Huey + huey-periodic
pip install z4j-django[arq]         # arq + arq-cron
pip install z4j-django[taskiq]      # TaskIQ + taskiq-scheduler
pip install z4j-django[all]         # every engine (CI / kitchen sink)
```

`pip install z4j-django` (no extra) installs only the framework adapter.
That's useful if you already manage engine packages elsewhere; otherwise
always pick an engine extra.

## Configure

Add `z4j_django` to your installed apps and set the `Z4J` dict in Django
settings:

```python
# settings.py
INSTALLED_APPS = [
    # ... your apps ...
    "z4j_django",
]

Z4J = {
    "brain_url": env("Z4J_BRAIN_URL"),   # e.g. "https://z4j.internal"
    "token":     env("Z4J_TOKEN"),       # minted in the brain dashboard
    "project_id": env("Z4J_PROJECT_ID", default="default"),
}
```

On `python manage.py runserver` (or `gunicorn`, `daphne`, `uvicorn`, ...)
the agent starts, connects to the brain, and z4j's dashboard populates
with every `@shared_task` and `@task` it discovers in your INSTALLED_APPS.

## What it does

| Piece | Purpose |
|---|---|
| `Z4JDjangoConfig.ready()` | Boots the agent once Django is fully loaded (after `INSTALLED_APPS` is populated) |
| Five-layer task discovery | Walks `INSTALLED_APPS` to find `@shared_task` / `@app.task` declarations |
| Django auth bridge | Maps the signed-in Django user to `z4j_core.User` for audit-log stamping |
| `django.core.checks` | Surfaces misconfiguration at `manage.py check` time |
| Optional admin embed | Renders a read-only "z4j agent status" panel in the Django admin |

## Reliability

`z4j-django` follows the project-wide safety rule: **z4j never breaks
your Django process**. Agent failures are caught at the boundary, logged,
and swallowed. Your runserver, gunicorn, and ASGI workers are never
affected by a z4j issue.

## Documentation

- [Quickstart (Django)](https://z4j.dev/getting-started/quickstart-django/)
- [Install guide](https://z4j.dev/getting-started/install/)
- [Architecture](https://z4j.dev/concepts/architecture/)

## License

Apache 2.0 - see [LICENSE](LICENSE). Your Django application is never
AGPL-tainted by importing `z4j_django`.

## Links

- Homepage: <https://z4j.com>
- Documentation: <https://z4j.dev>
- Issues: <https://github.com/z4jdev/z4j-django/issues>
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Security: `security@z4j.com` (see [SECURITY.md](SECURITY.md))
