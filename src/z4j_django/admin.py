"""Optional Django admin embed for z4j.

Phase 1: this module is intentionally minimal. The full
"read-only z4j panel inside Django admin" feature lands in Phase 1.1
once the brain dashboard ships and we have something to embed.

For now, the only thing here is a stub function that the framework
adapter's :meth:`register_admin_view` calls. It's a no-op so users
who set ``Z4J["django_admin_embed"] = True`` don't get an error.
"""

from __future__ import annotations

from typing import Any


def register_admin_panel(view: Any) -> None:  # noqa: ARG001
    """Register a z4j panel inside Django admin.

    No-op in Phase 1. The Phase 1.1 implementation will mount a
    Django view at ``/admin/z4j/`` that proxies to the brain's
    REST API using the current admin user's session.
    """
    return None


__all__ = ["register_admin_panel"]
