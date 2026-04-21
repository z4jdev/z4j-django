"""Per-request context capture for Django.

Django does not expose "the current request" anywhere by default, so
we provide a tiny middleware that stashes the request object on a
``ContextVar`` for the duration of the request. The framework
adapter's :meth:`current_context` reads from that ContextVar and
builds a :class:`z4j_core.models.RequestContext`.

Adding the middleware is optional - if it is not in
``MIDDLEWARE``, ``current_context()`` returns ``None`` (the agent
handles that gracefully). Users who want their events tagged with
the user ID, tenant, request ID, or trace ID add this middleware to
their settings::

    MIDDLEWARE = [
        ...
        "z4j_django.context.Z4JContextMiddleware",
        ...
    ]
"""

from __future__ import annotations

import logging
import weakref
from contextvars import ContextVar
from typing import Any
from uuid import UUID

from asgiref.sync import iscoroutinefunction, markcoroutinefunction

from z4j_core.models import RequestContext, User

logger = logging.getLogger("z4j.agent.django.context")

# We store a *weak reference* to the request rather than the request
# itself. ContextVar semantics + ``asyncio.create_task`` make this a
# real concern: if a view fires off ``asyncio.create_task(coro())``,
# the spawned task captures the current Context at create-time, which
# includes our ContextVar. After the response is returned and the
# middleware's ``finally`` block calls ``.reset(token)``, the spawned
# task's captured Context still holds the old request object - keeping
# it (and its user, session, headers, body) alive long after Django
# considers the request "done". A weakref makes the leak self-healing:
# once Django releases the request the spawned task sees ``None``.
_current_request: ContextVar["weakref.ReferenceType[Any] | None"] = ContextVar(
    "_z4j_django_current_request", default=None,
)


class Z4JContextMiddleware:
    """Stashes the request on a ContextVar for the agent to read.

    Standard Django middleware. Adds zero observable behavior to the
    request - only sets and clears a ContextVar.

    Implements Django's "hybrid sync/async middleware" contract: the
    constructor inspects ``get_response`` once, and ``__call__`` is
    re-marked as a coroutine when the chain is async. This is the
    pattern Django itself uses internally - see
    ``django.utils.deprecation.MiddlewareMixin``. The previous
    ``__acall__`` method on the class was wrong: Django never calls
    ``__acall__``; the only way to be an async middleware is to make
    ``__call__`` a coroutine and mark it via
    :func:`asgiref.sync.markcoroutinefunction`.

    Args:
        get_response: The next middleware / view in the chain.
                      Standard Django middleware contract.
    """

    sync_capable = True
    async_capable = True

    def __init__(self, get_response: Any) -> None:
        self.get_response = get_response
        # Pick the right call shape *once*. Django asks the middleware
        # whether it is a coroutine via asyncio.iscoroutinefunction(),
        # so we mark __call__ when needed.
        if iscoroutinefunction(get_response):
            self._is_async = True
            markcoroutinefunction(self)
        else:
            self._is_async = False

    def __call__(self, request: Any) -> Any:
        if self._is_async:
            return self._async_call(request)
        token = _current_request.set(_safe_ref(request))
        try:
            return self.get_response(request)
        finally:
            _current_request.reset(token)

    async def _async_call(self, request: Any) -> Any:
        token = _current_request.set(_safe_ref(request))
        try:
            return await self.get_response(request)
        finally:
            _current_request.reset(token)


def _safe_ref(request: Any) -> "weakref.ReferenceType[Any] | None":
    """Return a weakref to ``request``, or None if it can't be weak-ref'd.

    Django's ``HttpRequest`` supports weakrefs; certain test stubs
    (``unittest.mock.Mock`` instances, plain dicts) do not. Returning
    None on failure means the agent simply won't see request context
    for that request, which is the right fail-closed behaviour - it
    NEVER means we hold the request strongly and leak it.
    """
    try:
        return weakref.ref(request)
    except TypeError:
        return None


def current_request() -> Any | None:
    """Return the current Django request, or ``None`` if outside a request.

    Returns ``None`` from inside coroutines spawned via
    ``asyncio.create_task`` *after* the originating request has
    finished and Django has released it - the weak reference goes
    dead and callers correctly observe "no current request" rather
    than seeing a stale snapshot.

    Tolerant about what's stored on the ContextVar: the middleware
    writes a ``weakref.ref`` (so spawned tasks don't pin the
    request strongly), but tests and ad-hoc callers can also store
    the request directly. We accept both for backward compatibility.
    """
    value = _current_request.get()
    if value is None:
        return None
    if isinstance(value, weakref.ReferenceType):
        return value()
    return value


def current_request_context() -> RequestContext | None:
    """Build a :class:`RequestContext` from the current Django request.

    Returns ``None`` when:

    - There is no current request (e.g. inside a Celery worker, or
      :class:`Z4JContextMiddleware` is not installed).
    - The middleware is installed but for some reason the ContextVar
      is empty.

    Best-effort: any exception while inspecting the request is
    swallowed and ``None`` is returned. The agent's signal handlers
    must never crash because of context enrichment.
    """
    request = current_request()
    if request is None:
        return None

    try:
        user_id = _resolve_user_id(request)
        tenant_id = _resolve_tenant_id(request)
        request_id = _resolve_request_id(request)
        trace_id = _resolve_trace_id(request)
    except Exception:  # noqa: BLE001
        logger.debug("z4j: failed to derive request context", exc_info=True)
        return None

    return RequestContext(
        user_id=user_id,
        tenant_id=tenant_id,
        request_id=request_id,
        trace_id=trace_id,
        extra={},
    )


def current_user() -> User | None:
    """Return the authenticated Django user as a :class:`z4j_core.models.User`.

    Returns ``None`` when there is no current request, the user is
    anonymous, or the user object cannot be coerced into the z4j
    shape (e.g. a custom user model with no email).
    """
    from z4j_django.auth import django_user_to_z4j_user

    request = current_request()
    if request is None:
        return None
    user = getattr(request, "user", None)
    if user is None:
        return None
    return django_user_to_z4j_user(user)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_user_id(request: Any) -> UUID | str | None:
    user = getattr(request, "user", None)
    if user is None or getattr(user, "is_anonymous", True):
        return None
    pk = getattr(user, "pk", None)
    if pk is None:
        return None
    if isinstance(pk, UUID):
        return pk
    return str(pk)


def _resolve_tenant_id(request: Any) -> UUID | str | None:
    """Look for ``request.tenant``, ``request.organization``, or similar.

    z4j has no opinion on multi-tenancy - different apps use
    different conventions. We probe a few common attribute names and
    return whichever we find first.
    """
    for attr in ("tenant", "organization", "org", "workspace"):
        value = getattr(request, attr, None)
        if value is None:
            continue
        pk = getattr(value, "pk", value)
        if pk is None:
            continue
        if isinstance(pk, UUID):
            return pk
        return str(pk)
    return None


def _resolve_request_id(request: Any) -> str | None:
    """Common request-id middleware sets ``request.id`` or a header."""
    request_id = getattr(request, "id", None) or getattr(request, "request_id", None)
    if request_id:
        return str(request_id)[:100]
    headers = getattr(request, "headers", None)
    if headers is not None:
        for header in ("X-Request-Id", "X-Correlation-Id", "X-Amzn-Trace-Id"):
            value = headers.get(header)
            if value:
                return str(value)[:100]
    return None


def _resolve_trace_id(request: Any) -> str | None:
    """W3C ``traceparent`` header → trace id."""
    headers = getattr(request, "headers", None)
    if headers is None:
        return None
    traceparent = headers.get("traceparent")
    if not traceparent:
        return None
    # Format: "00-<trace-id>-<span-id>-<flags>"
    parts = traceparent.split("-")
    if len(parts) >= 2:
        return parts[1][:100]
    return None


__all__ = [
    "Z4JContextMiddleware",
    "current_request",
    "current_request_context",
    "current_user",
]
