"""Tests for ``z4j_django.context``."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest

from z4j_django.context import (
    Z4JContextMiddleware,
    _current_request,
    current_request,
    current_request_context,
    current_user,
)


class TestCurrentRequest:
    def test_no_request_returns_none(self) -> None:
        assert current_request() is None

    def test_set_via_context_var(self) -> None:
        request = SimpleNamespace(method="GET")
        token = _current_request.set(request)
        try:
            assert current_request() is request
        finally:
            _current_request.reset(token)


class _WeakRefableRequest:
    """Minimal request stand-in that supports ``weakref.ref(...)``.

    The middleware stores a ``weakref.ref`` (audit medium
    ``django-contextvar-leak``) so spawned tasks don't pin the
    request strongly. ``types.SimpleNamespace`` does NOT support
    weakrefs, so middleware tests use this class instead.
    """

    __slots__ = ("method", "path", "__weakref__")

    def __init__(self, *, method: str = "GET", path: str = "/") -> None:
        self.method = method
        self.path = path


class TestMiddleware:
    def test_middleware_sets_and_resets(self) -> None:
        captured: list = []

        def get_response(request: object) -> str:
            captured.append(current_request())
            return "ok"

        middleware = Z4JContextMiddleware(get_response)
        request = _WeakRefableRequest(method="GET", path="/foo")
        result = middleware(request)
        assert result == "ok"
        assert captured == [request]
        # Cleared after the call.
        assert current_request() is None

    def test_middleware_weakref_does_not_pin_request(self) -> None:
        """Audit medium ``django-contextvar-leak`` regression test.

        After the request handler returns, the only strong ref to
        the request must be releasable - the ContextVar's stored
        weakref must NOT keep the request alive past the response.
        """
        import gc
        import weakref as _wr

        captured_ref: list = []

        def get_response(request: object) -> str:
            # Snapshot a weakref to the request from inside the
            # request scope so we can probe it after the response.
            captured_ref.append(_wr.ref(request))
            return "ok"

        middleware = Z4JContextMiddleware(get_response)
        request = _WeakRefableRequest()
        middleware(request)
        del request
        gc.collect()
        # The request was released; the weakref we captured inside
        # the handler must now resolve to None.
        assert captured_ref[0]() is None


class TestCurrentRequestContext:
    def test_no_request_returns_none(self) -> None:
        assert current_request_context() is None

    def test_with_authenticated_user(self) -> None:
        user = SimpleNamespace(
            pk=42,
            is_anonymous=False,
            is_authenticated=True,
            email="alice@example.com",
        )
        request = SimpleNamespace(user=user, headers={})
        token = _current_request.set(request)
        try:
            ctx = current_request_context()
        finally:
            _current_request.reset(token)
        assert ctx is not None
        assert ctx.user_id == "42"

    def test_with_anonymous_user(self) -> None:
        user = SimpleNamespace(is_anonymous=True, is_authenticated=False)
        request = SimpleNamespace(user=user, headers={})
        token = _current_request.set(request)
        try:
            ctx = current_request_context()
        finally:
            _current_request.reset(token)
        assert ctx is not None
        assert ctx.user_id is None

    def test_request_id_from_header(self) -> None:
        user = SimpleNamespace(is_anonymous=True, is_authenticated=False)
        request = SimpleNamespace(
            user=user,
            headers={"X-Request-Id": "req_abc123"},
        )
        token = _current_request.set(request)
        try:
            ctx = current_request_context()
        finally:
            _current_request.reset(token)
        assert ctx is not None
        assert ctx.request_id == "req_abc123"

    def test_trace_id_from_traceparent(self) -> None:
        user = SimpleNamespace(is_anonymous=True, is_authenticated=False)
        request = SimpleNamespace(
            user=user,
            headers={
                "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b9c7c989f97918e1-01",
            },
        )
        token = _current_request.set(request)
        try:
            ctx = current_request_context()
        finally:
            _current_request.reset(token)
        assert ctx is not None
        assert ctx.trace_id == "0af7651916cd43dd8448eb211c80319c"


class TestCurrentUser:
    def test_no_request_returns_none(self) -> None:
        assert current_user() is None

    def test_anonymous_returns_none(self) -> None:
        user = SimpleNamespace(is_anonymous=True, is_authenticated=False)
        request = SimpleNamespace(user=user)
        token = _current_request.set(request)
        try:
            assert current_user() is None
        finally:
            _current_request.reset(token)

    def test_authenticated_user_resolves(self) -> None:
        user = SimpleNamespace(
            pk=UUID("00000000-0000-4000-8000-000000000001"),
            is_anonymous=False,
            is_authenticated=True,
            email="alice@example.com",
            is_superuser=False,
            is_active=True,
            username="alice",
            last_login=None,
        )

        from datetime import UTC, datetime

        user.date_joined = datetime.now(UTC)
        request = SimpleNamespace(user=user)
        token = _current_request.set(request)
        try:
            z4j_user = current_user()
        finally:
            _current_request.reset(token)
        assert z4j_user is not None
        assert z4j_user.email == "alice@example.com"
