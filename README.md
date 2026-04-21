# z4j-django

[![PyPI version](https://img.shields.io/pypi/v/z4j-django.svg)](https://pypi.org/project/z4j-django/)
[![Python](https://img.shields.io/pypi/pyversions/z4j-django.svg)](https://pypi.org/project/z4j-django/)
[![License](https://img.shields.io/pypi/l/z4j-django.svg)](https://github.com/z4jdev/z4j-django/blob/main/LICENSE)


**License:** Apache 2.0
**Status:** v1.0.0 - first public release.

Django framework adapter for [z4j](https://z4j.com). Drops into any
Django project via `INSTALLED_APPS` and bootstraps a z4j agent on
Django startup - no boilerplate, no signal wiring, no custom management
commands.

## Install

```bash
pip install z4j-django z4j-celery z4j-celerybeat
```

Pick the engine adapter(s) that match your stack:

```bash
pip install z4j-django z4j-rq z4j-rqscheduler
pip install z4j-django z4j-dramatiq z4j-apscheduler
pip install z4j-django z4j-huey z4j-hueyperiodic
```

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
