"""Async GitHub REST client with typed failures and a shared request budget."""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from urllib.parse import quote

import httpx
import jwt

from treestamp import sources
from treestamp.sources import TreeRecord
from treestamp_web import __version__

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from treestamp_web.config import Config

TREE_BODY_CAP = 32 * 1024 * 1024
BODY_CAP = 4 * 1024 * 1024
BLOB_CONCURRENCY = 8
JSON_MEDIA = "application/vnd.github+json"
SHA_MEDIA = "application/vnd.github.sha"
RAW_MEDIA = "application/vnd.github.raw+json"
_HEX40 = re.compile(r"[0-9a-f]{40}")
_REDIRECTS = (301, 302, 307, 308)
JWT_LIFETIME = 540  # seconds; GitHub allows at most 600
TOKEN_MARGIN = 300  # mint a fresh installation token this long before expiry
BUDGET_RETRY_SECONDS = 5


class GitHubError(Exception):
    def __init__(self, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class NotFoundError(GitHubError):
    """The repository, ref, or object is absent, private, moved, or empty."""


class TooLargeError(GitHubError):
    """The listing or a response body exceeds what the service handles."""


class UnavailableError(GitHubError):
    """GitHub failed, is rate limiting, or the service's budget is exhausted."""


class UpstreamTimeoutError(GitHubError):
    """GitHub did not answer within the configured timeout."""


@dataclass
class Budget:
    """Remaining requests in the current window, taken from response headers.

    Concurrent responses arrive out of order, so within one reset window the
    minimum ``remaining`` wins; a later window replaces an earlier one.
    """

    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None

    def observe(self, headers: Mapping[str, str]) -> None:
        try:
            limit = int(headers["x-ratelimit-limit"])
            remaining = int(headers["x-ratelimit-remaining"])
            reset = int(headers["x-ratelimit-reset"])
        except (KeyError, ValueError):
            return
        self.observe_values(limit, remaining, reset)

    def observe_values(self, limit: int, remaining: int, reset: int) -> None:
        if self.reset is None or reset > self.reset:
            self.limit, self.remaining, self.reset = limit, remaining, reset
        elif reset == self.reset and self.remaining is not None:
            self.limit = limit
            self.remaining = min(self.remaining, remaining)

    def effective_reserve(self, reserve: int) -> int:
        return reserve if self.limit is None else min(reserve, self.limit // 10)

    def exhausted(self, reserve: int) -> bool:
        return self.remaining is not None and self.remaining < self.effective_reserve(
            reserve
        )

    def retry_after(self, now: float) -> int:
        if self.reset is None:
            return 60
        return max(1, int(self.reset - now) + 1)

    def to_dict(self) -> dict[str, int | None]:
        return {"limit": self.limit, "remaining": self.remaining, "reset": self.reset}


@dataclass(frozen=True)
class Resolved:
    commit: str
    tree: str


@dataclass(frozen=True)
class PublicRepository:
    identity: int
    default_branch: str


def _repository_identity(data: object, full_name: str) -> PublicRepository:
    """Validate stable identity before deciding whether acquisition is allowed."""
    if not isinstance(data, dict):
        raise UnavailableError("unexpected GitHub response for repository")
    identity, branch = data.get("id"), data.get("default_branch")
    name = data.get("full_name")
    if (
        type(identity) is not int
        or identity <= 0
        or not isinstance(branch, str)
        or not branch.strip()
        or not isinstance(name, str)
        or name.lower() != full_name.lower()
    ):
        raise UnavailableError("unexpected GitHub response for repository")
    return PublicRepository(identity, branch)


@dataclass
class AppCredential:
    """A GitHub App acting for itself: a signed JWT buys installation tokens.

    ``client_id`` is the App's Client ID, which GitHub recommends as the JWT
    issuer; the numeric App ID is accepted there too.
    """

    client_id: str
    installation_id: str
    private_key: str
    token: str | None = None
    expires: float = 0.0

    def jwt(self, now: float) -> str:
        claims = {
            "iat": int(now) - 60,
            "exp": int(now) + JWT_LIFETIME,
            "iss": self.client_id,
        }
        return jwt.encode(claims, self.private_key, algorithm="RS256")

    def fresh(self, now: float) -> bool:
        return self.token is not None and now < self.expires - TOKEN_MARGIN


def _expiry(value: object, now: float) -> float:
    if isinstance(value, str):
        with contextlib.suppress(ValueError):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC).timestamp()
    return now + 3600


def _quote_ref(ref: str) -> str:
    """Slashes stay literal; GitHub accepts them in refs and httpx would unescape."""
    return quote(ref, safe="/")


def _json(body: bytes, what: str) -> object:
    try:
        return json.loads(body)
    except ValueError as exc:
        raise UnavailableError(f"unexpected GitHub response for {what}") from exc


class GitHubClient:
    def __init__(
        self,
        config: Config,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        headers = {
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"treestamp-web/{__version__}",
        }
        self._token = config.github_token
        self._app: AppCredential | None = None
        if config.github_app_client_id and config.github_app_installation_id:
            self._app = AppCredential(
                config.github_app_client_id,
                config.github_app_installation_id,
                config.github_app_private_key or "",
            )
        self._minting = asyncio.Lock()
        self._recovering = asyncio.Lock()
        self._next_budget_probe = 0.0
        self._http = httpx.AsyncClient(
            base_url=config.github_api_url,
            headers=headers,
            timeout=httpx.Timeout(config.request_timeout_seconds, connect=5.0),
            follow_redirects=False,
            transport=transport,
        )
        self._reserve = config.github_rate_reserve
        self._clock = clock
        self._blob_slots = asyncio.Semaphore(BLOB_CONCURRENCY)
        self.budget = Budget()
        self.calls = 0

    async def aclose(self) -> None:
        await self._http.aclose()

    @property
    def credential(self) -> str:
        """Which credential the client uses: ``app``, ``token``, or ``none``."""
        if self._app is not None:
            return "app"
        return "token" if self._token else "none"

    async def _bearer(self, *, refresh: bool = False) -> str | None:
        if self._app is None:
            return self._token
        now = self._clock()
        if self._app.fresh(now) and not refresh:
            return self._app.token
        async with self._minting:
            now = self._clock()
            if self._app.fresh(now) and not refresh:
                return self._app.token
            await self._mint(now)
            return self._app.token

    async def _mint(self, now: float) -> None:
        """Exchange a signed JWT for an installation access token."""
        assert self._app is not None
        installation = quote(self._app.installation_id, safe="")
        path = f"/app/installations/{installation}/access_tokens"
        try:
            response = await self._http.post(
                path,
                headers={
                    "Accept": JSON_MEDIA,
                    "Authorization": f"Bearer {self._app.jwt(now)}",
                },
            )
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("GitHub did not respond in time") from exc
        except httpx.HTTPError as exc:
            raise UnavailableError(
                f"GitHub request failed: {exc.__class__.__name__}"
            ) from exc
        self.calls += 1
        if response.status_code != 201:
            detail = ""
            with contextlib.suppress(ValueError, AttributeError, TypeError):
                detail = str(json.loads(response.content).get("message", ""))[:200]
            raise UnavailableError(
                f"GitHub App token exchange failed with status {response.status_code}"
                + (f": {detail}" if detail else "")
            )
        data = _json(response.content, "installation token")
        if not isinstance(data, dict) or not isinstance(data.get("token"), str):
            raise UnavailableError("unexpected GitHub response for installation token")
        self._app.token = str(data["token"])
        self._app.expires = _expiry(data.get("expires_at"), now)

    async def seed_budget(self) -> None:
        """Learn the budget without spending it; failure here is not fatal."""
        try:
            await self._refresh_budget()
        except GitHubError:
            return

    async def _refresh_budget(self) -> None:
        body, _ = await self._get(
            "/rate_limit", accept=JSON_MEDIA, cap=BODY_CAP, guarded=False
        )
        data = _json(body, "rate limit")
        resources = data.get("resources") if isinstance(data, dict) else None
        core = resources.get("core") if isinstance(resources, dict) else None
        if isinstance(core, dict):
            with contextlib.suppress(KeyError, TypeError, ValueError):
                self.budget.observe_values(
                    int(core["limit"]), int(core["remaining"]), int(core["reset"])
                )

    async def _guard_budget(self) -> None:
        if not self.budget.exhausted(self._reserve):
            return
        async with self._recovering:
            if not self.budget.exhausted(self._reserve):
                return
            now = self._clock()
            reset = self.budget.reset
            if reset is not None and now >= max(reset, self._next_budget_probe):
                self._next_budget_probe = now + BUDGET_RETRY_SECONDS
                with contextlib.suppress(GitHubError):
                    await self._refresh_budget()
                if not self.budget.exhausted(self._reserve):
                    return
            retry = max(
                self.budget.retry_after(now), int(self._next_budget_probe - now) + 1
            )
            raise UnavailableError(
                "the service's GitHub API budget is exhausted", retry_after=retry
            )

    async def _get(
        self,
        path: str,
        *,
        accept: str,
        cap: int,
        params: Mapping[str, str] | None = None,
        guarded: bool = True,
        retried: bool = False,
    ) -> tuple[bytes, httpx.Headers]:
        if guarded:
            await self._guard_budget()
        bearer = await self._bearer()
        self.calls += 1
        chunks: list[bytes] = []
        size = 0
        headers = {"Accept": accept}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        try:
            async with self._http.stream(
                "GET", path, params=params, headers=headers
            ) as response:
                self.budget.observe(response.headers)
                if (
                    response.status_code == 401
                    and self._app is not None
                    and not retried
                ):
                    # The installation token was revoked or expired early: mint anew.
                    await self._bearer(refresh=True)
                    return await self._get(
                        path,
                        accept=accept,
                        cap=cap,
                        params=params,
                        guarded=guarded,
                        retried=True,
                    )
                if response.status_code != 200:
                    raise self._failure(response)
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > cap:
                        raise TooLargeError("a GitHub response exceeds the size limit")
                    chunks.append(chunk)
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError("GitHub did not respond in time") from exc
        except httpx.HTTPError as exc:
            raise UnavailableError(
                f"GitHub request failed: {exc.__class__.__name__}"
            ) from exc
        return b"".join(chunks), response.headers

    def _failure(self, response: httpx.Response) -> GitHubError:
        status = response.status_code
        if status in _REDIRECTS:
            return NotFoundError(
                "repository was moved or renamed; use its current address"
            )
        if status == 401:
            return UnavailableError("GitHub rejected the service's credential")
        if status == 404:
            return NotFoundError("repository, ref, or path not found, or not public")
        if status == 422:
            return NotFoundError("ref not found in this repository")
        if status == 409:
            return NotFoundError("repository is empty")
        if status == 451:
            return NotFoundError("repository is unavailable for legal reasons")
        if status == 429 or (status == 403 and self._is_rate_limited(response.headers)):
            return UnavailableError(
                "GitHub is rate limiting the service",
                retry_after=self._retry_after(response.headers),
            )
        if status == 403:
            return NotFoundError("repository is not accessible")
        return UnavailableError(f"GitHub returned status {status}")

    @staticmethod
    def _is_rate_limited(headers: httpx.Headers) -> bool:
        return "retry-after" in headers or headers.get("x-ratelimit-remaining") == "0"

    def _retry_after(self, headers: httpx.Headers) -> int:
        header = headers.get("retry-after")
        if header is not None and header.isdigit():
            return max(1, int(header))
        if headers.get("x-ratelimit-remaining") == "0":
            return self.budget.retry_after(self._clock())
        return 60

    async def public_repository(self, owner: str, repo: str) -> PublicRepository:
        """Authorize acquisition using public visibility and stable repository id."""
        body, _ = await self._get(
            f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}",
            accept=JSON_MEDIA,
            cap=BODY_CAP,
        )
        data = _json(body, "repository")
        metadata = _repository_identity(data, f"{owner}/{repo}")
        assert isinstance(data, dict)
        if data.get("private") is not False or data.get("visibility") != "public":
            raise NotFoundError("repository is not public")
        return metadata

    async def resolve(self, owner: str, repo: str, ref: str) -> Resolved:
        """Resolve a branch, tag, or commit id to commit and tree ids."""
        base = f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
        if _HEX40.fullmatch(ref):
            commit = ref
        else:
            body, _ = await self._get(
                f"{base}/commits/{_quote_ref(ref)}", accept=SHA_MEDIA, cap=BODY_CAP
            )
            commit = body.decode("ascii", "replace").strip()
            if not _HEX40.fullmatch(commit):
                raise UnavailableError("unexpected GitHub response for ref")
        body, _ = await self._get(
            f"{base}/git/commits/{commit}", accept=JSON_MEDIA, cap=BODY_CAP
        )
        data = _json(body, "commit")
        tree = data.get("tree", {}).get("sha") if isinstance(data, dict) else None
        if not isinstance(tree, str) or not _HEX40.fullmatch(tree):
            raise UnavailableError("unexpected GitHub response for commit")
        return Resolved(commit, tree)

    async def tree(self, owner: str, repo: str, tree_id: str) -> list[TreeRecord]:
        """Fetch the complete listing; truncated or oversized listings fail."""
        base = f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
        body, _ = await self._get(
            f"{base}/git/trees/{tree_id}",
            accept=JSON_MEDIA,
            cap=TREE_BODY_CAP,
            params={"recursive": "1"},
        )
        data = _json(body, "tree")
        if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
            raise UnavailableError("unexpected GitHub response for tree")
        rows: list[object] = data["tree"]
        if data.get("truncated"):
            raise TooLargeError(
                "GitHub truncates listings above 100,000 entries or 7 MB; "
                "this repository is too large to preview"
            )
        if len(rows) > sources.MAX_ENTRIES:
            raise TooLargeError("the repository listing exceeds the entry limit")
        records = []
        for row in rows:
            if not isinstance(row, dict) or not all(
                isinstance(row.get(key), str) for key in ("path", "mode", "type", "sha")
            ):
                raise UnavailableError("unexpected GitHub tree row")
            records.append(
                TreeRecord(row["path"], row["mode"], row["type"], row["sha"])
            )
        return records

    async def blob(
        self, owner: str, repo: str, object_id: str, *, cap: int | None = None
    ) -> bytes:
        """Fetch raw blob bytes, for symlink targets and documents."""
        base = f"/repos/{quote(owner, safe='')}/{quote(repo, safe='')}"
        async with self._blob_slots:
            body, _ = await self._get(
                f"{base}/git/blobs/{object_id}",
                accept=RAW_MEDIA,
                cap=BODY_CAP if cap is None else cap,
            )
        return body
