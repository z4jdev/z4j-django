"""z4j-django - Django framework adapter for z4j.

Public API:

- :class:`Z4JContextMiddleware` - optional middleware that captures
  the current Django request so events can be tagged with user /
  tenant / request id.
- :class:`DjangoFrameworkAdapter` - the framework adapter implementation.
- :func:`build_config_from_django` - read ``settings.Z4J`` + env vars.

End users typically just add ``"z4j_django"`` to ``INSTALLED_APPS``
and let :class:`apps.Z4JDjangoConfig` do the rest. See
``docs/ADAPTER.md §3``.

Licensed under Apache License 2.0.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from z4j_django.config import build_config_from_django
from z4j_django.context import Z4JContextMiddleware
from z4j_django.framework import DjangoFrameworkAdapter

# Report the installed wheel version (drift-proof - tracks the
# pyproject version automatically). Falls back to the z4j-core
# protocol version for source checkouts with no installed metadata.
try:
    __version__ = _pkg_version("z4j-django")
except PackageNotFoundError:
    from z4j_core.version import __version__  # type: ignore[no-redef]

# Tell Django to use our custom AppConfig.
default_app_config = "z4j_django.apps.Z4JDjangoConfig"

__all__ = [
    "DjangoFrameworkAdapter",
    "Z4JContextMiddleware",
    "__version__",
    "build_config_from_django",
    "default_app_config",
]
