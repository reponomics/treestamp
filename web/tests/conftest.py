"""Fixtures: a real Git repository served through a fake GitHub transport."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from treestamp_web.app import create_app
from treestamp_web.config import Config
from treestamp_web.localgit import FakeGitHub, FakeOptions, LocalRepository


@dataclass
class Repo:
    """Minimal copy of the root test fixture; kept local to this project."""

    path: Path

    def git(self, *args: str, input_bytes: bytes | None = None) -> str:
        # Signing is the developer's setting; a fixture commit must not wait on a key.
        signing = ["-c", "commit.gpgSign=false"] if args[:1] == ("commit",) else []
        result = subprocess.run(
            ["git", "-C", str(self.path), *signing, *args],
            capture_output=True,
            check=True,
            input=input_bytes,
        )
        return result.stdout.decode("utf-8", "surrogateescape")

    def write(self, rel: str, content: str = "") -> Path:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def commit(self, message: str = "checkpoint", *, stage: bool = True) -> str:
        if stage:
            self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD").strip()


class Clock:
    def __init__(self, now: float = 1_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    path = tmp_path / "repo"
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    fixture = Repo(path)
    fixture.git("config", "user.email", "test@example.invalid")
    fixture.git("config", "user.name", "Test")
    fixture.git("config", "core.symlinks", "true")
    return fixture


def layout(repo: Repo) -> str:
    """A layout that exercises every record kind and the codec's quoting."""
    repo.write("sub/deep/leaf.txt", "x")
    repo.write("sub/other.txt", "y")
    repo.write("top.txt", "z")
    repo.write('quote "me".txt', "q")
    repo.write("sub/run.sh", "#!/bin/sh\n").chmod(0o755)
    (repo.path / "link").symlink_to("sub/deep\n\ttarget")
    first = repo.commit()
    bad = repo.git("hash-object", "-w", "--stdin", input_bytes=b"raw\xff\xfe").strip()
    repo.git("update-index", "--add", "--cacheinfo", f"120000,{bad},badlink")
    repo.git("update-index", "--add", "--cacheinfo", f"160000,{first},module")
    return repo.commit("with gitlink and byte symlink", stage=False)


@pytest.fixture
def fake(repo: Repo) -> FakeGitHub:
    layout(repo)
    return FakeGitHub(LocalRepository(repo.path), FakeOptions())


def transport_for(fake: FakeGitHub) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        status, headers, body = fake.respond(
            request.url.path,
            dict(request.url.params),
            request.headers.get("accept", ""),
            method=request.method,
            authorization=request.headers.get("authorization", ""),
        )
        return httpx.Response(status, headers=headers, content=body)

    return httpx.MockTransport(handler)


def make_config(**overrides: object) -> Config:
    values: dict[str, object] = {
        "github_api_url": "http://fake",
        "github_rate_reserve": 0,
    }
    values.update(overrides)
    return Config(**values)  # type: ignore[arg-type]


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def client(fake: FakeGitHub, clock: Clock) -> Iterator[TestClient]:
    app = create_app(make_config(), transport=transport_for(fake), clock=clock)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def repo_fake_with_app(repo: Repo) -> tuple[FakeGitHub, str]:
    """A fake that requires a valid App JWT for token exchange and a token for reads."""
    from .test_github import rsa_keys

    layout(repo)
    private, public = rsa_keys()
    return FakeGitHub(
        LocalRepository(repo.path), FakeOptions(app_public_key=public)
    ), private


def transport_for_fake(fake: FakeGitHub) -> httpx.MockTransport:
    return transport_for(fake)
