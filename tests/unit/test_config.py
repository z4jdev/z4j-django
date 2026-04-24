"""Tests for ``z4j_django.config.build_config_from_django``."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.conf import settings

from z4j_core.errors import ConfigError
from z4j_core.models import Config
from z4j_django.config import build_config_from_django


class TestRequiredFields:
    def test_all_required_from_dict(self, z4j_settings: dict) -> None:
        config = build_config_from_django()
        assert isinstance(config, Config)
        assert config.project_id == "test-project"

    def test_missing_dict_raises(self) -> None:
        with pytest.raises(ConfigError, match="missing required"):
            build_config_from_django()

    def test_partial_dict_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "Z4J", {"brain_url": "https://x"}, raising=False)
        with pytest.raises(ConfigError, match="missing required"):
            build_config_from_django()

    def test_dict_must_be_a_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "Z4J", "not-a-dict", raising=False)
        with pytest.raises(ConfigError, match="must be a dict"):
            build_config_from_django()


class TestEnvVarOverride:
    def test_env_overrides_dict(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("Z4J_PROJECT_ID", "from-env")
        config = build_config_from_django()
        assert config.project_id == "from-env"

    def test_env_only_works_without_dict(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("Z4J_BRAIN_URL", "https://z4j.example.com")
        monkeypatch.setenv("Z4J_TOKEN", "z4j_agent_envtest_" + "a" * 44)
        monkeypatch.setenv("Z4J_PROJECT_ID", "env-project")
        config = build_config_from_django()
        assert config.project_id == "env-project"

    def test_env_brain_url_overrides_invalid_dict(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            settings,
            "Z4J",
            {
                "brain_url": "https://wrong.example.com",
                "token": "z4j_agent_test_" + "a" * 44,
                "project_id": "test",
            },
            raising=False,
        )
        monkeypatch.setenv("Z4J_BRAIN_URL", "https://right.example.com")
        config = build_config_from_django()
        assert "right.example.com" in str(config.brain_url)


class TestOptionalFields:
    def test_environment_from_dict(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        z4j_settings["environment"] = "staging"
        monkeypatch.setattr(settings, "Z4J", z4j_settings, raising=False)
        config = build_config_from_django()
        assert config.environment == "staging"

    def test_dev_mode_from_env(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("Z4J_DEV_MODE", "true")
        config = build_config_from_django()
        assert config.dev_mode is True

    def test_dev_mode_truthy_strings(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("Z4J_DEV_MODE", "1")
        assert build_config_from_django().dev_mode is True

    def test_engines_csv(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("Z4J_ENGINES", "celery,rq")
        config = build_config_from_django()
        assert config.engines == ["celery", "rq"]

    def test_buffer_path_from_env(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Env-sourced buffer paths must live inside the allowed roots.

        ``~/.z4j`` is always the primary allowed root; the clamp
        resolves it at call time so this test doesn't need to touch
        ``HOME``. Audit 2026-04-24 Low-2 - the resolver now rejects
        buffer paths outside ``~/.z4j`` / ``$TMPDIR/z4j-{uid}``.
        """
        from z4j_bare.storage import primary_buffer_root

        allowed = primary_buffer_root() / "django-test.sqlite"
        monkeypatch.setenv("Z4J_BUFFER_PATH", str(allowed))
        config = build_config_from_django()
        assert config.buffer_path == allowed

    def test_buffer_path_outside_allowed_roots_rejected(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """The clamp refuses to open a SQLite buffer outside the
        agent's allowed roots (audit 2026-04-24 Low-2).
        """
        monkeypatch.setenv("Z4J_BUFFER_PATH", str(tmp_path / "x.sqlite"))
        with pytest.raises(ConfigError, match="must be inside one of"):
            build_config_from_django()

    def test_int_env_var_validation(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("Z4J_HEARTBEAT_SECONDS", "not-an-int")
        with pytest.raises(ConfigError, match="must be an integer"):
            build_config_from_django()

    def test_redaction_extras(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        z4j_settings["redaction"] = {
            "extra_key_patterns": ["customer_secret"],
            "extra_value_patterns": [r"acme_[A-Za-z0-9]{20,}"],
            "default_patterns_enabled": True,
        }
        monkeypatch.setattr(settings, "Z4J", z4j_settings, raising=False)
        config = build_config_from_django()
        assert config.redaction_extra_key_patterns == ["customer_secret"]
        assert config.redaction_defaults_enabled is True
