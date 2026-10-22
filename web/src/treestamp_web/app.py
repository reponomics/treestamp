"""FastAPI application: routes, error mapping, static page, and logging."""

from __future__ import annotations

import json
import logging
import os
import time
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from treestamp.errors import MarkerError
from treestamp_web import __version__
from treestamp_web.config import Config
from treestamp_web.github import (
    GitHubClient,
    GitHubError,
    NotFoundError,
    TooLargeError,
    UnavailableError,
    UpstreamTimeoutError,
)
from treestamp_web.limits import RateLimiter
from treestamp_web.preview import (
    PreviewError,
    PreviewService,
    parse_op_request,
    parse_preview_body,
    parse_request,
)
from treestamp_web.proxy import cloudflare_identity
from treestamp_web.routing import bind_session, replay_response

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    import httpx

STATIC = Path(__file__).parent / "static"
RESERVED_PREFIXES = frozenset(("api", "static", "healthz"))
DEFAULT_RETRY_AFTER = 60
SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-cache",
}
_GITHUB_STATUS: dict[type[GitHubError], tuple[int, str]] = {
    NotFoundError: (404, "not_found"),
    TooLargeError: (413, "too_large"),
    UnavailableError: (503, "upstream_unavailable"),
    UpstreamTimeoutError: (504, "upstream_timeout"),
}
logger = logging.getLogger("treestamp_web")


def _package_version() -> str:
    try:
        return version("treestamp")
    except PackageNotFoundError:
        return "unknown"


def _error(
    status: int,
    code: str,
    message: str,
    retry_after: int | None = None,
    extra: dict[str, object] | None = None,
) -> JSONResponse:
    message = message.encode("utf-8", "backslashreplace").decode("utf-8")
    error: dict[str, object] = {"code": code, "message": message}
    if extra:
        error.update(extra)
    headers = {}
    if retry_after is not None:
        error["retry_after"] = retry_after
        headers["Retry-After"] = str(retry_after)
    return JSONResponse({"error": error}, status_code=status, headers=headers)


def _log(event: str, **fields: object) -> None:
    record = {"ts": round(time.time(), 3), "event": event, **fields}
    logger.info(json.dumps(record, sort_keys=True))


def _context(request: Request) -> dict[str, object]:
    """Whatever the preview route had learned before it failed."""
    return {
        key: value
        for key in ("owner", "repo")
        if (value := getattr(request.state, key, None)) is not None
    }


def _github_status(exc: GitHubError) -> tuple[int, str]:
    for kind, mapping in _GITHUB_STATUS.items():
        if isinstance(exc, kind):
            return mapping
    return 503, "upstream_unavailable"


def create_app(
    config: Config | None = None,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    settings = config if config is not None else Config.from_env(os.environ)
    machine = settings.session_machine_id
    logging.basicConfig(level=settings.log_level.upper(), format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        client = GitHubClient(settings, transport=transport, clock=clock)
        await client.seed_budget()
        app.state.client = client
        app.state.service = PreviewService(client, settings, clock)
        try:
            yield
        finally:
            app.state.service.close()
            await client.aclose()

    app = FastAPI(
        title="treestamp preview",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.config = settings
    app.state.limiter = RateLimiter(settings.rate_limit_per_minute, clock)
    app.state.op_limiter = RateLimiter(settings.op_rate_limit_per_minute, clock)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Any) -> Response:
        response = await _routing_response(request, machine, settings.max_state_bytes)
        if response is None:
            response = await call_next(request)
        bind_session(request, response, machine)
        for name, value in SECURITY_HEADERS.items():
            # A route may set its own caching (the favicon does); others revalidate.
            if name == "Cache-Control" and name in response.headers:
                continue
            response.headers[name] = value
        return response

    @app.exception_handler(PreviewError)
    async def preview_error(request: Request, exc: PreviewError) -> JSONResponse:
        _log(
            "preview_rejected",
            status=exc.status,
            code=exc.code,
            message=str(exc),
            **_context(request),
        )
        return _error(exc.status, exc.code, str(exc), exc.retry_after, exc.extra)

    @app.exception_handler(GitHubError)
    async def github_error(request: Request, exc: GitHubError) -> JSONResponse:
        status, code = _github_status(exc)
        retry_after = exc.retry_after
        if status == 503 and retry_after is None:
            retry_after = DEFAULT_RETRY_AFTER
        _log(
            "upstream_failure",
            status=status,
            code=code,
            message=str(exc),
            **_context(request),
        )
        return _error(status, code, str(exc), retry_after)

    @app.exception_handler(MarkerError)
    async def marker_error(request: Request, exc: MarkerError) -> JSONResponse:
        _log(
            "preview_rejected",
            status=422,
            code="curation",
            message=str(exc),
            **_context(request),
        )
        return _error(422, "curation", str(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error(400, "invalid_settings", "invalid request parameters")

    @app.get("/healthz")
    async def healthz(request: Request) -> JSONResponse:
        client: GitHubClient = request.app.state.client
        service: PreviewService = request.app.state.service
        return JSONResponse(
            {
                "status": "ok",
                "package": _package_version(),
                "web": __version__,
                "build_commit": settings.build_commit,
                "credential": client.credential,
                "token_configured": client.credential != "none",
                "budget": client.budget.to_dict(),
                "cache": service.stats(),
            }
        )

    @app.api_route("/api/preview", methods=["GET", "POST"])
    async def preview(request: Request) -> JSONResponse:
        identity = _client_identity(request, settings)
        request.state.client = identity
        wait = request.app.state.limiter.acquire(identity)
        if wait is not None:
            raise PreviewError(
                429,
                "rate_limited",
                "too many requests from this client",
                retry_after=wait,
            )
        if request.method == "POST":
            data = await _json_body(
                request, settings.max_state_bytes, "invalid_settings"
            )
            parsed = parse_preview_body(data)
        else:
            parsed = parse_request(dict(request.query_params))
        request.state.owner = parsed.repository.owner
        request.state.repo = parsed.repository.name
        client: GitHubClient = request.app.state.client
        service: PreviewService = request.app.state.service
        started, calls = clock(), client.calls
        result = await service.preview(parsed)
        _log(
            "preview",
            owner=parsed.repository.owner,
            repo=parsed.repository.name,
            commit=result.commit,
            root=parsed.root,
            status=200,
            github_calls=client.calls - calls,
            budget_remaining=client.budget.remaining,
            duration_ms=round((clock() - started) * 1000),
        )
        return JSONResponse(result.to_dict(settings.public_base_url))

    @app.post("/api/op")
    async def operation(request: Request) -> JSONResponse:
        identity = _client_identity(request, settings)
        request.state.client = identity
        wait = request.app.state.op_limiter.acquire(identity)
        if wait is not None:
            raise PreviewError(
                429,
                "rate_limited",
                "too many operations from this client",
                retry_after=wait,
            )
        data = await _json_body(request, settings.max_state_bytes, "invalid_op")
        parsed = parse_op_request(data)
        request.state.owner = parsed.repository.owner
        request.state.repo = parsed.repository.name
        client: GitHubClient = request.app.state.client
        service: PreviewService = request.app.state.service
        started, calls = clock(), client.calls
        result = await service.apply(parsed)
        _log(
            "op",
            owner=parsed.repository.owner,
            repo=parsed.repository.name,
            commit=result.commit,
            op=parsed.op.type,
            status=200,
            github_calls=client.calls - calls,
            duration_ms=round((clock() - started) * 1000),
        )
        return JSONResponse(result.to_dict(settings.public_base_url))

    @app.get("/")
    async def home(request: Request) -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @app.get("/favicon.ico")
    async def favicon(request: Request) -> FileResponse:
        # Browsers request this path regardless of the page's link elements.
        return FileResponse(
            STATIC / "favicon.ico",
            media_type="image/x-icon",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    @app.get("/{owner}/{repository}")
    async def page(request: Request, owner: str, repository: str) -> Response:
        if owner in RESERVED_PREFIXES or owner == "favicon.ico":
            return _error(404, "not_found", "no such route")
        return FileResponse(STATIC / "index.html", media_type="text/html")

    return app


async def _routing_response(
    request: Request, machine: str | None, limit: int
) -> Response | None:
    response = replay_response(request, machine)
    if response is None or request.method != "POST":
        return response
    try:
        # Fly cannot replay bodies over 1 MB. Enforce the smaller application
        # limit even when the request would otherwise bypass the local route.
        await _bounded_body(request, limit)
    except PreviewError as exc:
        return _error(exc.status, exc.code, str(exc))
    return response


async def _json_body(request: Request, limit: int, code: str) -> object:
    body = await _bounded_body(request, limit)
    try:
        return json.loads(body)
    except (ValueError, RecursionError):
        raise PreviewError(400, code, "request body must be JSON") from None


async def _bounded_body(request: Request, limit: int) -> bytes:
    """Refuse oversized bodies before buffering them."""
    declared = request.headers.get("content-length")
    if declared is not None and (not declared.isdigit() or int(declared) > limit):
        raise PreviewError(
            413, "state_too_large", "request body exceeds the state limit"
        )
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise PreviewError(
                413, "state_too_large", "request body exceeds the state limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _client_identity(request: Request, config: Config) -> str:
    if config.cloudflare_networks:
        return cloudflare_identity(request, config.cloudflare_networks)
    if config.trust_proxy:
        forwarded = request.headers.get(config.client_ip_header)
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
