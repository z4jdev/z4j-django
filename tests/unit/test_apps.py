"""Tests for z4j_django.apps helpers."""

from __future__ import annotations

import pytest
from z4j_django.apps import _is_management_command


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        # z4j's own diagnostic/control commands must NOT autostart an agent
        # (B14: a second agent clobbers the pidfile + drops the running WS).
        (["manage.py", "z4j_doctor"], True),
        (["manage.py", "z4j_check"], True),
        (["manage.py", "z4j_status"], True),
        (["manage.py", "z4j_restart"], True),
        (["manage.py", "z4j_reconcile"], True),
        # Standard one-shot Django commands: skip.
        (["manage.py", "migrate"], True),
        (["manage.py", "collectstatic"], True),
        # Long-running app commands: DO autostart the agent.
        (["manage.py", "runserver"], False),
        (["manage.py", "runserver_plus"], False),
        # A user's own app command: autostart (the app is running).
        (["manage.py", "my_business_command"], False),
        ([], False),
    ],
)
def test_is_management_command(argv, expected, monkeypatch):
    monkeypatch.setattr("sys.argv", argv)
    assert _is_management_command() is expected
