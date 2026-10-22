"""Bytes at the process boundary, on whatever platform the suite runs on.

`run_cli` captures standard output through a `StringIO`, which never translates
newlines, so it cannot see what the real stream does with them. These tests run
the CLI as a subprocess and read raw bytes, because the documented onboarding
path is to redirect or paste this output into a document that `check` later
compares byte for byte. A treestamp that gains carriage returns on the way out
of a pipe is a different document from the one the tool would have written.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import treestamp
from tests.conftest import Repo
from treestamp.document import Document, render_region
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings, initial_tree

# The subprocess gets the source tree explicitly, so these run the same whether or
# not the package happens to be installed in the interpreter running the suite.
SOURCE = str(Path(treestamp.__file__).resolve().parents[1])


def cli(
    repo: Repo, *args: str, check: bool = True
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, "-m", "treestamp", *args],
        cwd=repo.path,
        capture_output=True,
        check=check,
        env={**os.environ, "PYTHONPATH": SOURCE},
    )


def cli_bytes(repo: Repo, *args: str) -> bytes:
    """Standard output of a real `treestamp` process, untouched."""
    return cli(repo, *args).stdout


def stamped(repo: Repo) -> Repo:
    repo.write("src/main.py", "print('hi')\n")
    repo.write("docs/guide.md", "# Guide\n")
    repo.add(".")
    repo.commit()
    return repo


def expected_region(repo: Repo) -> bytes:
    settings = Settings()
    target = capture_snapshot(repo.path, None)
    tree = initial_tree(target.tree, settings)
    document = Document(tree, settings)
    return render_region(document, ".").encode("utf-8")


def test_print_writes_the_treestamp_as_line_feeds(repo: Repo) -> None:
    output = cli_bytes(stamped(repo), "--print")
    assert b"\r\n" not in output
    assert output == expected_region(repo)


def test_explicit_tui_print_has_identical_bytes(repo: Repo) -> None:
    stamped(repo)
    assert cli_bytes(repo, "tui", "--print") == cli_bytes(repo, "--print")


def test_redirecting_print_produces_a_document_check_calls_current(
    repo: Repo, tmp_path: Path
) -> None:
    """The onboarding path: send `--print` to a file, then maintain that file."""
    stamped(repo)
    destination = repo.path / "README.md"
    destination.write_bytes(cli_bytes(repo, "--print"))
    assert b"\r\n" not in destination.read_bytes()
    repo.add("README.md")
    cli(repo, "update", "README.md")
    result = cli(repo, "check", "README.md", check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert b"Current" in result.stdout


def test_a_crlf_document_keeps_its_carriage_returns_through_update(
    repo: Repo,
) -> None:
    """The counterpart: a document already using CRLF is maintained in CRLF."""
    stamped(repo)
    destination = repo.path / "README.md"
    destination.write_bytes(cli_bytes(repo, "--print").replace(b"\n", b"\r\n"))
    repo.add("README.md")
    cli(repo, "update", "README.md")
    content = destination.read_bytes()
    assert b"\r\n" in content
    assert b"\n" not in content.replace(b"\r\n", b"")


def test_headless_hash_collision_update_and_check_preserve_authored_notes(
    repo: Repo,
) -> None:
    from treestamp.document import parse_document

    stamped(repo)
    repo.write("notes  # draft.md")
    repo.add("notes  # draft.md")
    output = cli_bytes(repo, "--print")
    assert b'special_paths = ["notes  # draft.md"]' in output
    output = output.replace(
        b"notes  # draft.md\n", b"notes  # draft.md  # Keep # this note\n"
    )
    output = output.replace(
        b"src/ (1 file)\n", b"src/ (1 file)  # Keep ## this # note too\n"
    )
    destination = repo.path / "README.md"
    before = (
        b"# Intro\r\n\r\n" + output.replace(b"\n", b"\r\n") + b"\r\nAfter the tree.\r\n"
    )
    destination.write_bytes(before)
    repo.add("README.md")
    cli(repo, "update", "README.md")
    before = destination.read_bytes()
    assert cli(repo, "check", "README.md").returncode == 0
    assert destination.read_bytes() == before
    repo.write("src/extra.py")
    repo.add("src/extra.py")
    assert cli(repo, "check", "README.md", check=False).returncode == 1
    assert destination.read_bytes() == before
    cli(repo, "update", "README.md")
    after = destination.read_bytes()
    assert after.startswith(b"# Intro\r\n\r\n") and after.endswith(
        b"\r\nAfter the tree.\r\n"
    )
    assert b"\n" not in after.replace(b"\r\n", b"")
    saved = parse_document(after)
    assert (
        next(
            node for node in saved.tree.walk() if node.path == "notes  # draft.md"
        ).annotation
        == "Keep # this note"
    )
    assert cli(repo, "check", "README.md").returncode == 0
    cli(repo, "update", "README.md")
    assert destination.read_bytes() == after

    repo.git("rm", "--cached", "notes  # draft.md")
    assert cli(repo, "check", "README.md", check=False).returncode == 1
    assert destination.read_bytes() == after
    cli(repo, "update", "README.md")
    normalized = destination.read_bytes()
    assert b"special_paths" not in normalized
    assert b"src/ (2 files)  # Keep ## this # note too\r\n" in normalized
    assert normalized.startswith(b"# Intro\r\n\r\n")
    assert normalized.endswith(b"\r\nAfter the tree.\r\n")
    assert cli(repo, "check", "README.md").returncode == 0
    cli(repo, "update", "README.md")
    assert destination.read_bytes() == normalized


def test_headless_unrepresentable_growth_fails_without_writing(repo: Repo) -> None:
    stamped(repo)
    destination = repo.path / "README.md"
    before = cli_bytes(repo, "--print")
    destination.write_bytes(before)
    repo.add("README.md")
    repo.write("vendor [gitlink]")
    repo.add("vendor [gitlink]")
    for command in ("check", "update"):
        result = cli(repo, command, "README.md", check=False)
        assert result.returncode == 2
        assert b"cannot represent" in result.stderr
        assert destination.read_bytes() == before
    assert not list(repo.path.glob(".treestamp-*"))


@pytest.mark.parametrize("document", ["README.md", "🌲.md"])
def test_maintenance_emits_utf8_with_a_legacy_stdout_encoding(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, document: str
) -> None:
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252:strict")
    monkeypatch.setenv("PYTHONUTF8", "0")
    stamped(repo)
    destination = repo.path / document
    destination.write_bytes(cli_bytes(repo, "--print"))
    repo.add(document)
    updated = cli(repo, "update", document, check=False)
    assert updated.returncode == 0, updated.stderr
    assert updated.stdout.decode("utf-8").startswith("Updated: ")
    before = destination.read_bytes()
    current = cli(repo, "check", document, check=False)
    assert current.returncode == 0, current.stderr
    assert current.stdout.decode("utf-8").startswith("Current: ")
    repo.write("🌱.py")
    repo.add("🌱.py")
    drift = cli(repo, "check", document, check=False)
    assert drift.returncode == 1, drift.stderr
    assert "🌱.py" in drift.stdout.decode("utf-8")
    assert "├──" in drift.stdout.decode("utf-8")
    assert not drift.stderr
    assert destination.read_bytes() == before
