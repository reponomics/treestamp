"""Browser-driven tests: the page against a fake GitHub serving a fixture repository.

Requires pytest-playwright and a browser (`playwright install chromium`, or
`--browser-channel chrome` for an installed Google Chrome). The fixture
repository is built in a temporary directory with known contents, so the
tests never depend on this checkout.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

REPO = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Fixture:
    path: Path
    old_commit: str  # before the README was stamped; its tree differs from HEAD
    head: str


def _git(path: Path, *args: str) -> str:
    # Signing is the developer's setting; a fixture commit must not wait on a key.
    signing = ["-c", "commit.gpgSign=false"] if args[:1] == ("commit",) else []
    return subprocess.run(  # noqa: S603
        ["git", "-C", str(path), *signing, *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _build_fixture(path: Path) -> Fixture:
    """Three root directories, a few files, and a README stamped at HEAD."""
    from treestamp.document import Document, write_document
    from treestamp.gitio import capture_snapshot
    from treestamp.model import Settings
    from treestamp.session import TreeSession

    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)  # noqa: S603
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test")
    for rel, text in {
        "docs/guide.md": "# Guide\n",
        "docs/api.md": "# API\n",
        "scripts/run.sh": "#!/bin/sh\n",
        "src/app.py": "print('hi')\n",
        "src/util.py": "x = 1\n",
        "LICENSE": "MIT\n",
        "README.md": "# Fixture\n\n<!-- treestamp:start -->\n<!-- treestamp:end -->\n\nTail.\n",
    }.items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "files")
    old = _git(path, "rev-parse", "HEAD")
    settings = Settings()
    snapshot = capture_snapshot(path, "HEAD")
    session = TreeSession(snapshot.tree, settings)
    for node in snapshot.tree.walk():
        if node.is_dir:
            session.expand(node.path)
    for name in ("LICENSE", "README.md"):
        session.hide(name)
    write_document(
        Document(session.printed_tree(), settings, session.saved_hidden()),
        path / "README.md",
    )
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "stamp")
    return Fixture(path, old, _git(path, "rev-parse", "HEAD"))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait(url: str, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):  # noqa: S310
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError(f"{url} did not come up")


@pytest.fixture(scope="session")
def fixture_repo(tmp_path_factory: pytest.TempPathFactory) -> Fixture:
    return _build_fixture(tmp_path_factory.mktemp("browser") / "repo")


@pytest.fixture(scope="session")
def service(fixture_repo: Fixture) -> Iterator[str]:
    """A fake GitHub serving the fixture and the service; yields the base URL."""
    fake_port, app_port = _free_port(), _free_port()
    fake = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            str(REPO / "web/scripts/fake_github.py"),
            "--repo",
            str(fixture_repo.path),
            "--port",
            str(fake_port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    env = {
        **os.environ,
        "GITHUB_API_URL": f"http://127.0.0.1:{fake_port}",
        "GITHUB_RATE_RESERVE": "0",
        "RATE_LIMIT_PER_MINUTE": "1000",
        "OP_RATE_LIMIT_PER_MINUTE": "10000",
    }
    app = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "--factory",
            "treestamp_web.app:create_app",
            "--host",
            "127.0.0.1",
            "--port",
            str(app_port),
        ],
        cwd=REPO / "web",
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait(f"http://127.0.0.1:{fake_port}/rate_limit")
        _wait(f"http://127.0.0.1:{app_port}/healthz")
        yield f"http://127.0.0.1:{app_port}"
    finally:
        for process in (app, fake):
            process.terminate()
        for process in (app, fake):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


@pytest.fixture
def old_commit(fixture_repo: Fixture) -> str:
    return fixture_repo.old_commit
