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

    def test_dev_mode_from_env_is_rejected(
        self,
        z4j_settings: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """1.5 unified the security policy: Z4J_DEV_MODE env var is
        warn-and-ignored by every adapter. Pre-1.5 z4j-bare rejected
        it but Django/Flask/FastAPI silently honored it (audit C3
        drift). Operators who genuinely want dev_mode in non-prod
        set it in code (settings.Z4J["dev_mode"]) where the choice
        is auditable in source control.
        """
        import warnings

        monkeypatch.setenv("Z4J_DEV_MODE", "true")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            config = build_config_from_django()
        # Env-set dev_mode is dropped, defaults to False
        assert config.dev_mode is False
        # The security warning fires
        assert any("Z4J_DEV_MODE" in str(w.message) for w in caught)

    def test_dev_mode_from_settings_is_honored(
        self,
        z4j_settings: dict,
    ) -> None:
        """Explicit dev_mode in settings.Z4J is honored - it's
        operator code, not untrusted env. Same policy z4j-bare's
        ``install_agent(dev_mode=True)`` already enforced.
        """
        z4j_settings["dev_mode"] = True
        config = build_config_from_django()
        assert config.dev_mode is True

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
        """Explicit ``buffer_path`` in settings.Z4J is honored.

        1.5+: Z4J_BUFFER_PATH was dropped (consolidated into Z4J_HOME
        via z4j_core.paths). Operators who need a custom buffer
        location set ``buffer_path`` in ``settings.Z4J`` directly;
        explicit code-level settings are treated as authoritative.
        """
        from z4j_bare.storage import primary_buffer_root

        allowed = primary_buffer_root() / "django-test.sqlite"
        z4j_settings["buffer_path"] = str(allowed)
        config = build_config_from_django()
        assert config.buffer_path == allowed

    def test_buffer_path_in_settings_passes_through(
        self,
        z4j_settings: dict,
        tmp_path: Path,
    ) -> None:
        """Explicit settings paths pass through unmodified.

        1.5: the audit 2026-04-24 Low-2 clamp was specifically about
        UNTRUSTED env vars. Explicit ``settings.Z4J["buffer_path"]``
        is operator code, treated as authoritative. The Z4J_BUFFER_PATH
        env var that the clamp protected against was dropped entirely
        in 1.5; setting it triggers a startup error via
        ``reject_deprecated_path_env``.
        """
        explicit = tmp_path / "x.sqlite"
        z4j_settings["buffer_path"] = str(explicit)
        config = build_config_from_django()
        assert config.buffer_path == explicit

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
