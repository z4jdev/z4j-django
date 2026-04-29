"""z4j-django CLI: ``z4j-django <subcommand>`` and ``python -m z4j_django``.

Standalone entry point that mirrors the Django management commands
(``manage.py z4j_doctor``, ``z4j_check``, ``z4j_status``,
``z4j_restart``) for environments where ``manage.py`` isn't
convenient: containers without the Django app on the host's PYTHONPATH,
multi-framework hosts running both Django and Flask, ad-hoc shell
invocations.

Subcommand surface (inherited from z4j_bare.cli):

- ``doctor``  - full probe ladder + JSON output option
- ``check``   - compact pass/fail
- ``status``  - one-line current state (lists every running agent)
- ``restart`` / ``reload`` - SIGHUP the django agent's pidfile
- ``run``, ``version`` - inherited verbatim from z4j-bare

The Django-specific config-from-settings path is only available
through the management commands (``manage.py z4j_doctor`` reads
``DJANGO_SETTINGS_MODULE``). The standalone form reads ``Z4J_*``
env vars only - intentional, so it stays callable without a Django
app context.
"""

from __future__ import annotations

from z4j_bare.cli import make_main_for_adapter

main = make_main_for_adapter("django")


__all__ = ["main"]
