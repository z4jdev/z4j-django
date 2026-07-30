"""B15 regression: ``_first_subcommand`` must consume EVERY value-taking
Celery global option's value, not only ``-A``/``--app``. Otherwise a
space-separated value like ``-b amqp://host`` was returned as the
"sub-command", so ``celery -A proj -b amqp://mq beat`` resolved to
``amqp://mq`` and the beat agent was skipped ("unknown" scheduler)."""

from __future__ import annotations

from z4j_django.apps import _first_subcommand


def test_app_flag_value_consumed() -> None:
    assert _first_subcommand(["-A", "proj.celery", "beat", "-l", "info"]) == "beat"


def test_broker_flag_value_consumed() -> None:
    # The exact B15 case: -b takes a value that must not be read as the cmd.
    assert _first_subcommand(["-A", "proj", "-b", "amqp://mq", "beat", "-l", "info"]) == "beat"


def test_multiple_value_opts_consumed() -> None:
    args = [
        "-A",
        "proj",
        "--broker",
        "amqp://mq",
        "--result-backend",
        "redis://r",
        "--workdir",
        "/srv/app",
        "worker",
    ]
    assert _first_subcommand(args) == "worker"


def test_equals_form_is_self_contained() -> None:
    assert _first_subcommand(["--broker=amqp://mq", "-A", "proj", "beat"]) == "beat"


def test_no_subcommand_returns_unknown() -> None:
    assert _first_subcommand(["-A", "proj", "-b", "amqp://mq"]) == "unknown"
