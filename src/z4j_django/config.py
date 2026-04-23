"""Build a :class:`z4j_core.models.Config` from Django settings + env vars.

Resolution priority (highest first):

1. ``Z4J_*`` environment variables
2. ``settings.Z4J`` dict in the user's Django settings module
3. Defaults declared on :class:`z4j_core.models.Config`

Why env vars beat the settings dict: production deployments
typically commit ``settings.py`` to source control and inject
secrets via the environment. The settings dict is the place to
declare *defaults*; the environment is where production values
land. Local dev usually only needs the dict.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from z4j_core.errors import ConfigError
from z4j_core.models import Config


def build_config_from_django() -> Config:
    """Read ``settings.Z4J`` and the environment, return a validated Config.

    Raises:
        ConfigError: Required values are missing or invalid.
    """
    # Lazy import - z4j_django is added to INSTALLED_APPS, which means
    # Django settings are already configured by the time this function
    # is called. We import here so unit tests of OTHER modules in this
    # package don't drag Django in unnecessarily.
    from django.conf import settings

    raw_dict = _read_settings_dict(settings)
    resolved = _resolve(raw_dict)
    try:
        return Config(**resolved)
    except ValidationError as exc:
        # Pydantic ValidationError stringifies the offending value as
        # part of its message. For Z4J that means a misformatted
        # ``token`` or ``hmac_secret`` would land in every Django
        # error log. Build a redacted summary from the error locations
        # + types only - no values, no input.
        details = [
            {
                "loc": ".".join(str(p) for p in err["loc"]),
                "type": err["type"],
            }
            for err in exc.errors()
        ]
        raise ConfigError(
            f"invalid Z4J configuration ({len(details)} field(s))",
            details={"errors": details},
        ) from None
    except (TypeError, ValueError) as exc:
        # Log the type only - never the value, since it could be a
        # secret coerced from a misconfigured env var.
        raise ConfigError(
            f"invalid Z4J configuration: {type(exc).__name__}",
        ) from None


def _read_settings_dict(settings: Any) -> dict[str, Any]:
    """Return ``settings.Z4J`` as a dict, or empty dict if missing.

    Accepts ``Z4J = {...}``. Anything else (including ``None``) is
    treated as "not configured at all" - the env vars become the
    only source.
    """
    raw = getattr(settings, "Z4J", None)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(
            f"settings.Z4J must be a dict, got {type(raw).__name__}",
        )
    return dict(raw)


def _resolve(settings_dict: dict[str, Any]) -> dict[str, Any]:
    """Merge env vars on top of the settings dict + report missing required keys."""
    env = os.environ
    resolved: dict[str, Any] = {}

    # Required fields. Use ``is not None`` so an explicit empty
    # string is treated as "misconfigured", not "fall back to dict".
    # An operator who sets ``Z4J_TOKEN=""`` should get a clear error
    # instead of an opaque "brain rejected agent token" 60s later.
    brain_url = env.get("Z4J_BRAIN_URL") if env.get("Z4J_BRAIN_URL") is not None else settings_dict.get("brain_url")
    token = env.get("Z4J_TOKEN") if env.get("Z4J_TOKEN") is not None else settings_dict.get("token")
    project_id = env.get("Z4J_PROJECT_ID") if env.get("Z4J_PROJECT_ID") is not None else settings_dict.get("project_id")

    missing: list[str] = []
    if not brain_url:
        missing.append("brain_url (or Z4J_BRAIN_URL)")
    if not token:
        missing.append("token (or Z4J_TOKEN)")
    if not project_id:
        missing.append("project_id (or Z4J_PROJECT_ID)")
    if missing:
        raise ConfigError(
            "missing required Z4J settings: " + ", ".join(missing),
            details={"missing": missing},
        )

    resolved["brain_url"] = brain_url
    resolved["token"] = token
    resolved["project_id"] = project_id

    # HMAC secret - required in production by AgentRuntime.start().
    # Surface it from env or settings here so users get a clean error
    # at config-build time if it is missing in non-dev_mode.
    hmac_secret = env.get("Z4J_HMAC_SECRET") or settings_dict.get("hmac_secret")
    if hmac_secret:
        resolved["hmac_secret"] = hmac_secret

    # Agent name (optional human label). Allows multiple workers
    # sharing one bearer token to be told apart in the dashboard.
    # When unset the dashboard shows the name set at mint time.
    _maybe_set(resolved, settings_dict, env, "agent_name", "Z4J_AGENT_NAME")

    # Optional fields with env override
    _maybe_set(resolved, settings_dict, env, "environment", "Z4J_ENVIRONMENT")
    _maybe_set(resolved, settings_dict, env, "transport", "Z4J_TRANSPORT")
    _maybe_set(
        resolved, settings_dict, env, "log_level", "Z4J_LOG_LEVEL",
    )

    if "engines" in settings_dict:
        resolved["engines"] = settings_dict["engines"]
    elif "Z4J_ENGINES" in env:
        resolved["engines"] = [
            x.strip() for x in env["Z4J_ENGINES"].split(",") if x.strip()
        ]

    if "schedulers" in settings_dict:
        resolved["schedulers"] = settings_dict["schedulers"]
    elif "Z4J_SCHEDULERS" in env:
        resolved["schedulers"] = [
            x.strip() for x in env["Z4J_SCHEDULERS"].split(",") if x.strip()
        ]

    if "tags" in settings_dict and isinstance(settings_dict["tags"], dict):
        resolved["tags"] = settings_dict["tags"]

    # Booleans
    _maybe_set_bool(resolved, settings_dict, env, "dev_mode", "Z4J_DEV_MODE")
    _maybe_set_bool(resolved, settings_dict, env, "strict_mode", "Z4J_STRICT_MODE")
    _maybe_set_bool(resolved, settings_dict, env, "autostart", "Z4J_AUTOSTART")

    # Integers
    _maybe_set_int(
        resolved, settings_dict, env, "heartbeat_seconds", "Z4J_HEARTBEAT_SECONDS",
    )
    _maybe_set_int(
        resolved, settings_dict, env, "buffer_max_events", "Z4J_BUFFER_MAX_EVENTS",
    )
    _maybe_set_int(
        resolved, settings_dict, env, "buffer_max_bytes", "Z4J_BUFFER_MAX_BYTES",
    )
    _maybe_set_int(
        resolved, settings_dict, env, "max_payload_bytes", "Z4J_MAX_PAYLOAD_BYTES",
    )

    # Path
    if "buffer_path" in settings_dict:
        resolved["buffer_path"] = Path(settings_dict["buffer_path"])
    elif "Z4J_BUFFER_PATH" in env:
        resolved["buffer_path"] = Path(env["Z4J_BUFFER_PATH"])

    # Redaction nested dict
    redaction = settings_dict.get("redaction") or {}
    if isinstance(redaction, dict):
        if "extra_key_patterns" in redaction:
            resolved["redaction_extra_key_patterns"] = list(
                redaction["extra_key_patterns"],
            )
        if "extra_value_patterns" in redaction:
            resolved["redaction_extra_value_patterns"] = list(
                redaction["extra_value_patterns"],
            )
        if "default_patterns_enabled" in redaction:
            resolved["redaction_defaults_enabled"] = bool(
                redaction["default_patterns_enabled"],
            )

    return resolved


def _maybe_set(
    resolved: dict[str, Any],
    settings_dict: dict[str, Any],
    env: dict[str, str] | os._Environ[str],
    key: str,
    env_key: str,
) -> None:
    if env_key in env:
        resolved[key] = env[env_key]
    elif key in settings_dict:
        resolved[key] = settings_dict[key]


def _maybe_set_bool(
    resolved: dict[str, Any],
    settings_dict: dict[str, Any],
    env: dict[str, str] | os._Environ[str],
    key: str,
    env_key: str,
) -> None:
    if env_key in env:
        resolved[key] = env[env_key].strip().lower() in ("1", "true", "yes", "on")
    elif key in settings_dict:
        resolved[key] = bool(settings_dict[key])


def _maybe_set_int(
    resolved: dict[str, Any],
    settings_dict: dict[str, Any],
    env: dict[str, str] | os._Environ[str],
    key: str,
    env_key: str,
) -> None:
    if env_key in env:
        try:
            resolved[key] = int(env[env_key])
        except ValueError as exc:
            raise ConfigError(f"{env_key} must be an integer: {exc}") from exc
    elif key in settings_dict:
        resolved[key] = int(settings_dict[key])


__all__ = ["build_config_from_django"]
