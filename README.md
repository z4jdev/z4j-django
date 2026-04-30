# z4j-django

[![PyPI version](https://img.shields.io/pypi/v/z4j-django.svg)](https://pypi.org/project/z4j-django/)
[![Python](https://img.shields.io/pypi/pyversions/z4j-django.svg)](https://pypi.org/project/z4j-django/)
[![License](https://img.shields.io/pypi/l/z4j-django.svg)](https://github.com/z4jdev/z4j-django/blob/main/LICENSE)

The Django framework adapter for [z4j](https://z4j.com).

Adds the z4j agent into your Django project as a single
`INSTALLED_APPS` entry. Auto-discovers the engine adapter you
have installed (Celery, RQ, Dramatiq, Huey, arq, TaskIQ) and
streams every task lifecycle event to the brain.

## Install

```bash
pip install z4j-django z4j-celery z4j-celerybeat
```

Then add `"z4j_django"` to `INSTALLED_APPS` in your Django settings.

## Documentation

Full docs at [z4j.dev/frameworks/django/](https://z4j.dev/frameworks/django/).

## License

Apache-2.0 — see [LICENSE](LICENSE).

## Links

- Homepage: https://z4j.com
- Documentation: https://z4j.dev
- PyPI: https://pypi.org/project/z4j-django/
- Issues: https://github.com/z4jdev/z4j-django/issues
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Security: security@z4j.com (see [SECURITY.md](SECURITY.md))
