"""Build :class:`z4j_core.models.DiscoveryHints` from Django's app registry.

Walks ``django.apps.apps.get_app_configs()`` and collects every app's
filesystem path. Engine adapters (notably :mod:`z4j_celery`) use the
returned paths to find ``tasks.py`` files via static AST scanning -
they do not need to import the app modules themselves, which is
important during Django startup when not every app is fully loaded.

The discovery hint also includes the app *names* so engine adapters
that prefer to call ``importlib.import_module(name)`` (e.g. when
they want to support tasks declared in non-conventional locations)
have what they need.
"""

from __future__ import annotations

import logging
from pathlib import Path

from z4j_core.models import DiscoveryHints

logger = logging.getLogger("z4j.agent.django.discovery")


def collect_django_hints() -> DiscoveryHints:
    """Return :class:`DiscoveryHints` populated from Django's app registry.

    Returns an empty :class:`DiscoveryHints` (with ``framework_name="django"``)
    if Django is not yet ready or any error occurs - never raises.
    Discovery hints are advisory; engine adapters always have a
    fallback strategy.
    """
    from django.apps import apps  # local import - Django must be ready
    from django.apps.registry import AppRegistryNotReady

    paths: list[Path] = []
    names: list[str] = []

    try:
        configs = list(apps.get_app_configs())
    except AppRegistryNotReady:
        logger.debug("django app registry not ready; returning empty hints")
        return DiscoveryHints(framework_name="django")
    except Exception:  # noqa: BLE001
        logger.exception("failed to enumerate django app configs")
        return DiscoveryHints(framework_name="django")

    for config in configs:
        # Skip our own app - we never have ``tasks.py`` of our own to scan.
        if config.name == "z4j_django":
            continue
        try:
            app_path = Path(config.path)
            if app_path.is_dir():
                paths.append(app_path)
            names.append(config.name)
        except Exception:  # noqa: BLE001
            logger.exception(
                "could not resolve filesystem path for django app %s",
                config.name,
            )
            continue

    logger.debug("z4j discovery hints: %d django apps", len(paths))
    return DiscoveryHints(
        app_paths=paths,
        app_names=names,
        framework_name="django",
    )


__all__ = ["collect_django_hints"]
