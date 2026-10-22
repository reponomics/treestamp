"""Answer GitHub API requests from a local Git checkout.

Used by the test suite's mock transport and by ``scripts/fake_github.py``, so
the fake server and the tests cannot drift apart. Requires a ``git`` binary.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import unquote

from treestamp.sources import TreeRecord

if TYPE_CHECKING:
    from pathlib import Path

_REPO_PATH = re.compile(r"/repos/([^/]+)/([^/]+)(?:/(.*))?")
_WINDOW_SECONDS = 3600


@dataclass(frozen=True)
class LocalRepository:
    path: Path

    def _git(self, *args: str) -> bytes | None:
        result = subprocess.run(  # noqa: S603
            ["git", "-C", str(self.path), "-c", "core.quotePath=false", *args],
            capture_output=True,
            check=False,
        )
        return result.stdout if result.returncode == 0 else None

    def resolve(self, ref: str) -> str | None:
        raw = self._git(
            "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"
        )
        return raw.decode("ascii").strip() if raw else None

    def default_branch(self) -> str | None:
        """Use the fixture's symbolic HEAD, including nonstandard branch names."""
        raw = self._git("symbolic-ref", "--quiet", "--short", "HEAD")
        return raw.decode("utf-8").strip() if raw else None

    def tree_id(self, commit: str) -> str | None:
        raw = self._git(
            "rev-parse", "--verify", "--end-of-options", f"{commit}^{{tree}}"
        )
        return raw.decode("ascii").strip() if raw else None

    def records(self, tree_id: str) -> list[TreeRecord] | None:
        raw = self._git("ls-tree", "-r", "-t", "-z", "--full-tree", tree_id)
        if raw is None:
            return None
        records = []
        for row in raw.split(b"\0"):
            if not row:
                continue
            meta, _, path = row.partition(b"\t")
            mode, kind, object_id = (part.decode("ascii") for part in meta.split())
            records.append(
                TreeRecord(
                    path.decode("utf-8", "surrogateescape"), mode, kind, object_id
                )
            )
        return records

    def blob(self, object_id: str) -> bytes | None:
        return self._git("cat-file", "blob", object_id)


@dataclass
class FakeOptions:
    private: bool = False
    repository_id: int = 1
    truncated: bool = False
    rate_limit_after: int | None = None
    empty: bool = False
    only: str | None = None
    limit: int = 60
    app_public_key: str | None = None
    """PEM public key; when set, token exchanges must carry a JWT it verifies."""
    installation_id: str = "12345"


@dataclass
class FakeGitHub:
    """Route API paths to a local repository, with switchable failure modes."""

    repository: LocalRepository
    options: FakeOptions = field(default_factory=FakeOptions)
    requests: int = 0
    tokens_issued: int = 0

    def respond(
        self,
        path: str,
        query: dict[str, str],
        accept: str,
        *,
        method: str = "GET",
        authorization: str = "",
    ) -> tuple[int, dict[str, str], bytes]:
        self.requests += 1
        if method == "POST":
            return self._exchange(path, authorization)
        if self.options.app_public_key is not None and not authorization.startswith(
            "Bearer ghs_"
        ):
            return (
                401,
                {"content-type": "application/json"},
                _message("Bad credentials"),
            )
        remaining = max(0, self.options.limit - self.requests)
        reset = int(time.time()) + _WINDOW_SECONDS
        headers = {
            "x-ratelimit-limit": str(self.options.limit),
            "x-ratelimit-remaining": str(remaining),
            "x-ratelimit-reset": str(reset),
        }
        after = self.options.rate_limit_after
        if after is not None and self.requests > after:
            headers["x-ratelimit-remaining"] = "0"
            return 403, headers, _message("API rate limit exceeded")
        status, body = self._route(path, query, accept, reset, remaining)
        if isinstance(body, bytes):
            headers["content-type"] = "application/octet-stream"
            return status, headers, body
        headers["content-type"] = "application/json"
        return status, headers, json.dumps(body).encode()

    def _route(
        self, path: str, query: dict[str, str], accept: str, reset: int, remaining: int
    ) -> tuple[int, object]:
        if path == "/rate_limit":
            core = {"limit": self.options.limit, "remaining": remaining, "reset": reset}
            return 200, {"resources": {"core": core}}
        match = _REPO_PATH.fullmatch(path)
        if match is None:
            return 404, {"message": "Not Found"}
        owner, name, rest = match.groups()
        if self.options.only is not None and f"{owner}/{name}" != self.options.only:
            return 404, {"message": "Not Found"}
        if rest is None:
            return 200, {
                "id": self.options.repository_id,
                "full_name": f"{owner}/{name}",
                "private": self.options.private,
                "visibility": "private" if self.options.private else "public",
                "default_branch": self.repository.default_branch(),
            }
        if self.options.empty:
            return 409, {"message": "Git Repository is empty."}
        repo = self.repository
        if rest.startswith("commits/"):
            ref = unquote(rest[len("commits/") :])
            commit = repo.resolve(ref)
            if commit is None:
                return 422, {"message": f"No commit found for SHA: {ref}"}
            if accept == "application/vnd.github.sha":
                return 200, commit.encode("ascii")
            return 200, {
                "sha": commit,
                "commit": {"tree": {"sha": repo.tree_id(commit)}},
            }
        if rest.startswith("git/commits/"):
            commit = rest[len("git/commits/") :]
            tree = repo.tree_id(commit) if _is_hex(commit) else None
            if tree is None:
                return 404, {"message": "Not Found"}
            return 200, {"sha": commit, "tree": {"sha": tree}}
        if rest.startswith("git/trees/"):
            tree_id = rest[len("git/trees/") :]
            records = repo.records(tree_id) if _is_hex(tree_id) else None
            if records is None:
                return 404, {"message": "Not Found"}
            if query.get("recursive") != "1":
                records = [r for r in records if "/" not in r.path]
            rows = [
                {"path": r.path, "mode": r.mode, "type": r.type, "sha": r.object_id}
                for r in records
            ]
            return 200, {
                "sha": tree_id,
                "tree": rows,
                "truncated": self.options.truncated,
            }
        if rest.startswith("git/blobs/"):
            object_id = rest[len("git/blobs/") :]
            blob = repo.blob(object_id) if _is_hex(object_id) else None
            if blob is None:
                return 404, {"message": "Not Found"}
            if accept == "application/vnd.github.raw+json":
                return 200, blob
            encoded = base64.encodebytes(blob).decode("ascii")
            return 200, {"sha": object_id, "encoding": "base64", "content": encoded}
        return 404, {"message": "Not Found"}

    def _exchange(
        self, path: str, authorization: str
    ) -> tuple[int, dict[str, str], bytes]:
        """POST /app/installations/{id}/access_tokens, as the App flow uses it."""
        headers = {"content-type": "application/json"}
        expected = f"/app/installations/{self.options.installation_id}/access_tokens"
        if path != expected:
            return 404, headers, _message("Not Found")
        if self.options.app_public_key is not None:
            import jwt as pyjwt

            try:
                pyjwt.decode(
                    authorization.removeprefix("Bearer "),
                    self.options.app_public_key,
                    algorithms=["RS256"],
                )
            except pyjwt.PyJWTError as exc:
                return 401, headers, _message(f"Bad credentials: {exc}")
        self.tokens_issued += 1
        expires = time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + _WINDOW_SECONDS)
        )
        body = {"token": f"ghs_fake{self.tokens_issued}", "expires_at": expires}
        return 201, headers, json.dumps(body).encode()


def _is_hex(value: str) -> bool:
    return len(value) == 40 and all(c in "0123456789abcdef" for c in value)


def _message(text: str) -> bytes:
    return json.dumps({"message": text}).encode()
