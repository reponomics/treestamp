"""Cookie-based affinity using Fly's bounded replay and fallback protocol.

Replay caching is deliberately unused: Fly does not allow its timeout/fallback
fields with cached replays. See https://docs.fly.io/networking/dynamic-request-routing.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from starlette.responses import Response

if TYPE_CHECKING:
    from starlette.requests import Request

COOKIE = "__Host-treestamp-machine"
MAX_REPLAY_BODY = 1_000_000
_MACHINE_ID = re.compile(r"[0-9a-f]{14}")
_REPLAY_MARKERS = (
    "fly-replay-src",
    "fly-replay-failed",
    "fly-preferred-instance-unavailable",
)
_API_METHODS = {"/api/preview": {"GET", "POST"}, "/api/op": {"POST"}}


def valid_machine_id(value: str | None) -> str | None:
    return value if value is not None and _MACHINE_ID.fullmatch(value) else None


def _owner(request: Request) -> str | None:
    values = []
    for header in request.headers.getlist("cookie"):
        for part in header.split(";"):
            name, _, value = part.partition("=")
            if name.strip() == COOKIE:
                values.append(value.strip())
    return valid_machine_id(values[0]) if len(values) == 1 else None


def replay_response(request: Request, machine: str | None) -> Response | None:
    """Route once to this browser's owner; fallback must execute locally.

    Replay markers only disable routing. Even if a client supplies them, normal
    snapshot authorization and request validation still apply on this Machine.
    """
    if machine is None or request.method not in _API_METHODS.get(
        request.url.path, set()
    ):
        return None
    owner = _owner(request)
    if owner is None or owner == machine:
        return None
    if any(header in request.headers for header in _REPLAY_MARKERS):
        return None
    return Response(
        status_code=307,
        headers={"Fly-Replay": f"instance={owner};timeout=2s;fallback=prefer_self"},
    )


def bind_session(request: Request, response: Response, machine: str | None) -> None:
    """Only a successful load replaces the browser's existing session affinity."""
    if machine is None or request.url.path != "/api/preview":
        return
    if response.status_code != 200:
        return
    response.set_cookie(COOKIE, machine, secure=True, httponly=True, samesite="lax")
    response.headers["Cache-Control"] = "private, no-store"
