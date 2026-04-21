"""Django system checks for z4j_django.

Hooked into ``django.core.checks`` so ``manage.py check`` and any
``runserver`` startup will refuse to proceed if z4j_django is in
``INSTALLED_APPS`` but its configuration is incomplete or
mis-shaped.

These checks are deliberately STARTUP-time validation, not runtime
errors. We want users to know about problems before they push to
production, and we want CI to fail fast on configuration drift.

The checks themselves never crash Django - every check returns a
list of ``Error`` / ``Warning`` objects. The check framework
handles the rest.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning, register

# Check IDs follow the convention: ``z4j.<num>``.
_E_NOT_A_DICT = "z4j.E001"
_E_MISSING_REQUIRED = "z4j.E002"
_E_INVALID_BRAIN_URL = "z4j.E003"
_E_INVALID_PROJECT_ID = "z4j.E004"
_W_TOKEN_LOOKS_PLACEHOLDER = "z4j.W001"
_W_INSECURE_BRAIN_URL = "z4j.W002"
_W_MIDDLEWARE_MISSING = "z4j.W003"

_PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")
_PLACEHOLDER_PATTERNS = ("changeme", "replace", "your-token", "xxx")


@register()
def check_z4j_settings(
    app_configs: Any | None = None,  # noqa: ARG001
    **kwargs: Any,  # noqa: ARG001
) -> list[CheckMessage]:
    """Validate ``settings.Z4J`` and related env vars at startup.

    Returns a list of ``CheckMessage`` instances. An empty list
    means everything looks good.
    """
    raw = getattr(settings, "Z4J", None)
    if raw is None:
        return [
            Error(
                "z4j_django is in INSTALLED_APPS but settings.Z4J is missing.",
                hint=(
                    "Add a Z4J = {'brain_url': ..., 'token': ..., 'project_id': ...} "
                    "dict to settings.py, or set Z4J_BRAIN_URL, Z4J_TOKEN, and "
                    "Z4J_PROJECT_ID environment variables."
                ),
                id=_E_NOT_A_DICT,
            ),
        ]

    if not isinstance(raw, dict):
        return [
            Error(
                f"settings.Z4J must be a dict, got {type(raw).__name__}.",
                hint="Use Z4J = { ... } in your Django settings.",
                id=_E_NOT_A_DICT,
            ),
        ]

    issues: list[CheckMessage] = []
    issues.extend(_check_required(raw))
    issues.extend(_check_brain_url(raw))
    issues.extend(_check_project_id(raw))
    issues.extend(_check_token(raw))
    issues.extend(_check_middleware(settings))
    return issues


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_required(z4j_dict: dict[str, Any]) -> list[CheckMessage]:
    """Verify the three required keys are present in dict OR env."""
    import os

    missing: list[str] = []
    if not (z4j_dict.get("brain_url") or os.environ.get("Z4J_BRAIN_URL")):
        missing.append("brain_url (or Z4J_BRAIN_URL env var)")
    if not (z4j_dict.get("token") or os.environ.get("Z4J_TOKEN")):
        missing.append("token (or Z4J_TOKEN env var)")
    if not (z4j_dict.get("project_id") or os.environ.get("Z4J_PROJECT_ID")):
        missing.append("project_id (or Z4J_PROJECT_ID env var)")

    if not missing:
        return []
    return [
        Error(
            "Required Z4J configuration values are missing: " + ", ".join(missing),
            hint=(
                "Either fill them in your settings.Z4J dict or supply the matching "
                "Z4J_* environment variable."
            ),
            id=_E_MISSING_REQUIRED,
        ),
    ]


def _check_brain_url(z4j_dict: dict[str, Any]) -> list[CheckMessage]:
    import os

    url = z4j_dict.get("brain_url") or os.environ.get("Z4J_BRAIN_URL")
    if not url:
        return []  # already reported by _check_required

    url_str = str(url)
    issues: list[CheckMessage] = []

    # Use urlsplit so we can inspect every component, not just regex
    # the whole string. urllib.parse correctly rejects malformed
    # input by raising; the older _BRAIN_URL_RE silently accepted
    # things like ``https://user:pw@host?query=secret`` which would
    # then leak credentials in every check_message and log line.
    try:
        parts = urlsplit(url_str)
    except ValueError:
        return [
            Error(
                "Z4J brain_url is not a valid URL.",
                hint=(
                    "Use the form https://z4j.example.com "
                    "(no userinfo, no query string, no fragment)."
                ),
                id=_E_INVALID_BRAIN_URL,
            ),
        ]

    safe_display = f"{parts.scheme}://{parts.hostname or ''}"
    if parts.port:
        safe_display += f":{parts.port}"

    if parts.scheme not in ("http", "https") or not parts.hostname:
        return [
            Error(
                f"Z4J brain_url {safe_display!r} is not a valid HTTP(S) URL.",
                hint="Use the form https://z4j.example.com (no trailing path needed).",
                id=_E_INVALID_BRAIN_URL,
            ),
        ]

    # Reject embedded userinfo (``https://user:password@host``).
    # The token belongs in settings.Z4J["token"], not the URL - and
    # baking it into the URL puts it in every error message, log
    # line, and dashboard tooltip.
    if parts.username or parts.password:
        return [
            Error(
                f"Z4J brain_url {safe_display!r} contains embedded credentials; "
                "supply the token via settings.Z4J['token'] (or Z4J_TOKEN env var) "
                "instead.",
                hint="Strip the user:password@ portion from the URL.",
                id=_E_INVALID_BRAIN_URL,
            ),
        ]

    if parts.query or parts.fragment:
        return [
            Error(
                f"Z4J brain_url {safe_display!r} must not include a query string "
                "or fragment.",
                hint="Use just the scheme + host (+ optional port).",
                id=_E_INVALID_BRAIN_URL,
            ),
        ]

    host = parts.hostname or ""
    if parts.scheme == "http" and host not in ("localhost", "127.0.0.1", "::1"):
        issues.append(
            Warning(
                f"Z4J brain_url {safe_display!r} uses plain http://; production "
                "deployments must terminate TLS via a reverse proxy.",
                hint=(
                    "See docs/DEPLOYMENT.md §6.1 for the recommended Caddy / nginx "
                    "configuration."
                ),
                id=_W_INSECURE_BRAIN_URL,
            ),
        )
    return issues


def _check_project_id(z4j_dict: dict[str, Any]) -> list[CheckMessage]:
    import os

    project_id = z4j_dict.get("project_id") or os.environ.get("Z4J_PROJECT_ID")
    if not project_id:
        return []
    if not _PROJECT_ID_RE.match(str(project_id)):
        return [
            Error(
                f"Z4J project_id {project_id!r} is invalid.",
                hint=(
                    "Project ids must match ^[a-z0-9][a-z0-9-]{1,62}$ "
                    "(lowercase letters, digits, hyphens; 2-63 chars; "
                    "must not start with a hyphen)."
                ),
                id=_E_INVALID_PROJECT_ID,
            ),
        ]
    return []


def _check_token(z4j_dict: dict[str, Any]) -> list[CheckMessage]:
    import os

    token = z4j_dict.get("token") or os.environ.get("Z4J_TOKEN", "")
    token_str = str(token).lower() if token else ""
    if not token_str:
        return []
    if any(p in token_str for p in _PLACEHOLDER_PATTERNS):
        return [
            Warning(
                "Z4J token looks like a placeholder value.",
                hint=(
                    "Mint a real agent token from the dashboard "
                    "(Project → Add agent) and supply it via the Z4J_TOKEN "
                    "environment variable."
                ),
                id=_W_TOKEN_LOOKS_PLACEHOLDER,
            ),
        ]
    return []


def _check_middleware(settings_obj: Any) -> list[CheckMessage]:
    """Warn (not error) if context middleware is missing.

    The middleware is optional. We only warn - most users won't
    need request-context enrichment, and forcing it on everyone
    would be friction. The warning helps users who DO want it
    discover the right name.
    """
    middleware = getattr(settings_obj, "MIDDLEWARE", []) or []
    if "z4j_django.context.Z4JContextMiddleware" in middleware:
        return []
    return [
        Warning(
            (
                "z4j_django.context.Z4JContextMiddleware is not in MIDDLEWARE; "
                "task events will not include user / tenant / request id enrichment."
            ),
            hint=(
                "Add 'z4j_django.context.Z4JContextMiddleware' to MIDDLEWARE if "
                "you want events tagged with the originating user/tenant/request. "
                "This is optional - z4j works fine without it."
            ),
            id=_W_MIDDLEWARE_MISSING,
        ),
    ]


__all__ = ["check_z4j_settings"]
