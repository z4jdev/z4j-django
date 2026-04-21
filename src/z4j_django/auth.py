"""Convert a Django ``User`` instance into a :class:`z4j_core.models.User`.

The mapping is best-effort and tolerant of custom user models.
Required fields on the z4j model are filled with sensible defaults
when the Django user does not have them.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4, uuid5

from z4j_core.models import User

logger = logging.getLogger("z4j.agent.django.auth")


def django_user_to_z4j_user(user: Any) -> User | None:
    """Build a :class:`z4j_core.models.User` from a Django user.

    Returns ``None`` for anonymous users (Django's
    ``AnonymousUser``) and for any user without an email - the z4j
    User model requires a valid email and we should not invent one.

    Best-effort: any failure during conversion is swallowed and
    ``None`` is returned. The signal handlers that call this must
    never crash because of a custom user model quirk.
    """
    if user is None:
        return None
    if getattr(user, "is_anonymous", True):
        return None
    if not getattr(user, "is_authenticated", True):
        return None

    email = _safe_str(getattr(user, "email", None))
    if not email or "@" not in email:
        return None

    pk = getattr(user, "pk", None)
    user_id = _coerce_uuid(pk)

    try:
        return User(
            id=user_id,
            email=email,  # type: ignore[arg-type]
            display_name=_resolve_display_name(user),
            is_admin=bool(getattr(user, "is_superuser", False)),
            is_active=bool(getattr(user, "is_active", True)),
            force_password_change=False,
            timezone="UTC",
            last_login_at=getattr(user, "last_login", None),
            created_at=getattr(user, "date_joined", None) or datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    except Exception:  # noqa: BLE001
        logger.debug("z4j: failed to convert django user", exc_info=True)
        return None


def _resolve_display_name(user: Any) -> str | None:
    """Best-effort display name resolution."""
    for attr in ("get_full_name", "get_short_name"):
        method = getattr(user, attr, None)
        if callable(method):
            try:
                name = method()
                if name:
                    return str(name)[:200]
            except Exception:  # noqa: BLE001
                continue
    name = getattr(user, "username", None) or getattr(user, "name", None)
    if name:
        return str(name)[:200]
    return None


#: Stable namespace for the v5 derivation below. DO NOT change
#: this UUID once shipped - every Django user's z4j ``user_id``
#: is derived from it. A namespace change would break every audit
#: trail and rate-limit history that links by user_id.
_DJANGO_USER_NAMESPACE: UUID = UUID("ce4d6f6c-0aab-5b4f-9f5d-23a417cb29c1")


def _coerce_uuid(pk: Any) -> UUID:
    """Return a STABLE UUID for the Django user.

    Audit H15: the previous implementation called ``uuid4()`` on
    every event for users whose pk was not already a UUID (i.e.
    every Django default ``AutoField`` user). The same person was
    therefore recorded with a different ``user_id`` per event,
    making audit trails unlinkable, rate-limiting impossible, and
    "who did what" undetectable.

    This implementation derives a deterministic UUID5 from the
    Django pk under a fixed project-wide namespace
    (:data:`_DJANGO_USER_NAMESPACE`). Two events for the same
    user always produce the same z4j ``user_id``. Different
    Django pks always produce different z4j ``user_id``s.
    Callers can still recover the original pk by reading
    ``event.metadata.django_user_pk`` (which we set elsewhere).
    """
    if isinstance(pk, UUID):
        return pk
    if pk is None:
        # No user (anonymous request). The caller should NOT call
        # us in this case - guard so we never accidentally collapse
        # all anon traffic to a single id.
        return uuid4()
    try:
        key = str(pk)
    except Exception:  # noqa: BLE001
        return uuid4()
    return uuid5(_DJANGO_USER_NAMESPACE, f"django:{key}")


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(value)
    except Exception:  # noqa: BLE001
        return None


__all__ = ["django_user_to_z4j_user"]
