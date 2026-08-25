"""Reserved Django admin integration surface.

The current package does not embed the Brain dashboard in Django admin.
``register_admin_panel`` is intentionally a no-op; use the Brain dashboard
directly.
"""

from __future__ import annotations

from typing import Any


def register_admin_panel(view: Any) -> None:
    """Accept the reserved panel argument without registering a view."""
    return


__all__ = ["register_admin_panel"]
