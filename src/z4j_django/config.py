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

1.5: this module previously held ~250 lines of env-var parsing that
duplicated the same logic in z4j-flask, z4j-fastapi, and z4j-bare.
The resolver now lives in :mod:`z4j_core.config.resolver`; this file
is a thin shim that flattens ``settings.Z4J`` (including the nested
``redaction`` dict) into the resolver's expected ``framework_overrides``
shape.
"""

from __future__ import annotations

from typing import Any

from z4j_core.config import resolve_agent_config
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

    raw = getattr(settings, "Z4J", None)
    if raw is None:
        framework_overrides: dict[str, Any] = {}
    elif isinstance(raw, dict):
        framework_overrides = _flatten(raw)
    else:
        raise ConfigError(
            f"settings.Z4J must be a dict, got {type(raw).__name__}",
        )

    return resolve_agent_config(
        framework_name="django",
        framework_overrides=framework_overrides,
    )


def _flatten(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten Django's ``settings.Z4J`` shape for the unified resolver.

    Django supports nesting redaction settings under a ``redaction``
    sub-dict; the resolver expects them at the top level under their
    Config field names. Translate here so the resolver stays
    framework-agnostic.
    """
    out: dict[str, Any] = {k: v for k, v in raw.items() if k != "redaction"}
    redaction = raw.get("redaction") or {}
    if isinstance(redaction, dict):
        if "extra_key_patterns" in redaction:
            out["redaction_extra_key_patterns"] = list(
                redaction["extra_key_patterns"],
            )
        if "extra_value_patterns" in redaction:
            out["redaction_extra_value_patterns"] = list(
                redaction["extra_value_patterns"],
            )
        if "default_patterns_enabled" in redaction:
            out["redaction_defaults_enabled"] = bool(
                redaction["default_patterns_enabled"],
            )
    return out


__all__ = ["build_config_from_django"]
