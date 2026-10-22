"""Fixture repos: real git, real index, real documents."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest


def _options(args: tuple[str, ...]) -> list[str]:
    """Signing is the developer's setting; a fixture commit must not wait on a key."""
    return ["-c", "commit.gpgSign=false"] if args[:1] == ("commit",) else []


@dataclass
class Repo:
    path: Path

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.path), *_options(args), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout

    def git_bytes(self, *args: str, input: bytes | None = None) -> bytes:
        return subprocess.run(
            ["git", "-C", str(self.path), *_options(args), *args],
            input=input,
            capture_output=True,
            check=True,
        ).stdout

    def blob(self, content: bytes) -> str:
        return (
            self.git_bytes("hash-object", "-w", "--stdin", input=content)
            .decode()
            .strip()
        )

    def tree(self, entries: list[tuple[str, str, str, str]]) -> str:
        """Build Git objects without requiring their names to exist on the host OS."""
        data = b"".join(
            f"{mode} {kind} {oid}\t{name}\0".encode("utf-8", "surrogateescape")
            for mode, kind, oid, name in entries
        )
        return self.git_bytes("mktree", "-z", input=data).decode().strip()

    def write(self, rel: str, content: str = "") -> Path:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def write_bytes(self, rel: str, content: bytes) -> Path:
        target = self.path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return target

    def add(self, *paths: str) -> None:
        self.git("add", "--", *paths)

    def commit(self, message: str = "checkpoint") -> None:
        self.git("commit", "-q", "-m", message)

    def read(self, rel: str) -> str:
        return (self.path / rel).read_text(encoding="utf-8")

    def read_bytes(self, rel: str) -> bytes:
        return (self.path / rel).read_bytes()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    # A commit hook's index override belongs to the caller, not this fixture repo.
    monkeypatch.delenv("GIT_INDEX_FILE", raising=False)
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    fixture = Repo(tmp_path)
    fixture.git("config", "user.email", "test@example.invalid")
    fixture.git("config", "user.name", "Test")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    return fixture


def run_cli(*args: str) -> tuple[int, str, str]:
    """Invoke the CLI in-process (coverage-friendly)."""
    import contextlib
    import io

    from treestamp.cli import main

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(args))
    return code, out.getvalue(), err.getvalue()
