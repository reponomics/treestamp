"""Regression coverage for print command behavior."""

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tests.cli_fixtures import stamp
from tests.conftest import Repo, run_cli
from treestamp.document import Document, load_document, parse_document, write_document
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings, initial_tree


def test_unicode_subtree_root_is_repository_relative(repo: Repo) -> None:
    repo.write("🌲/keep.txt")
    repo.write("🌲/🌱.txt")
    repo.add(".")
    snapshot = capture_snapshot(repo.path / "🌲")
    tree = replace(
        snapshot.tree,
        children=tuple(
            node for node in snapshot.tree.children if node.path != "🌱.txt"
        ),
    )
    document = Document(tree, Settings(root="🌲"), frozenset({"🌲/🌱.txt"}))
    path = repo.path / "docs" / "tree.md"
    path.parent.mkdir()
    write_document(document, path, create=True)
    assert load_document(path)[0] == document
    assert run_cli("check", str(path.relative_to(repo.path)))[0] == 0
    assert (
        run_cli("load", str(path.relative_to(repo.path)), "--print")[1].encode("utf-8")
        == path.read_bytes()
    )


@pytest.mark.parametrize("arguments", [["check"], ["--print"], ["new", "--print"]])
def test_headless_commands_never_import_textual(
    repo: Repo, arguments: list[str]
) -> None:
    stamp(repo)
    source = str(Path(__file__).resolve().parents[1] / "src")
    script = f"import sys; from treestamp.cli import main; assert main({arguments!r}) == 0; assert not any(k == 'textual' or k.startswith('textual.') for k in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo.path,
        env={**os.environ, "PYTHONPATH": source},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("prefix", [(), ("new",)])
def test_print_new_is_exactly_one_level_and_hides_nothing(
    repo: Repo, prefix: tuple[str, ...]
) -> None:
    repo.write("src/pkg/main.py")
    repo.write("setup.cfg")
    repo.write("README.md", "ordinary prose\n")
    repo.add(".")
    before = repo.read("README.md")
    code, output, error = run_cli(*prefix, "--print")
    assert code == 0 and not error
    document = parse_document(output.encode())
    assert document.tree == initial_tree(capture_snapshot(repo.path).tree, Settings())
    assert not document.hidden
    assert "README.md" in output and "setup.cfg" in output
    assert "main.py" not in output and "(1 folder)" in output
    assert repo.read("README.md") == before


def test_print_load_extracts_without_updating_and_preserves_style(repo: Repo) -> None:
    path = stamp(repo)
    document, _ = load_document(path)
    assert document is not None
    repo.write("new.txt")
    repo.add("new.txt")
    for style in ("unicode", "ascii"):
        write_document(replace(document, settings=Settings(style=style)), path)
        before = path.read_bytes()
        code, output, error = run_cli(
            "load", str(path.relative_to(repo.path)), "--print"
        )
        assert code == 0 and not error and "new.txt" not in output
        assert output.encode() == before
        assert parse_document(output.encode()).settings.style == style
        assert path.read_bytes() == before


def test_default_absent_document_initializes_but_explicit_or_empty_is_error(
    repo: Repo,
) -> None:
    repo.write("app.py")
    repo.add(".")
    assert run_cli("--print")[0] == 0
    assert run_cli("load", "missing.md", "--print")[0] == 2
    repo.write("README.md", "<!-- treestamp:start -->\n<!-- treestamp:end -->\n")
    assert run_cli("--print")[0] == 2
    repo.write("README.md", "plain prose")
    assert run_cli("load", "README.md", "--print")[0] == 2


def test_binary_stdout_preserves_git_bytes_and_flushes_pending_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import io

    from treestamp.cli import _emit

    output = io.BytesIO()
    stream = io.TextIOWrapper(output, encoding="ascii", newline="\r\n")
    stream.write("pending\n")
    monkeypatch.setattr(sys, "stdout", stream)
    _emit("./\n└── byte\udcff\n")
    assert output.getvalue() == b"pending\r\n" + "./\n└── byte".encode() + b"\xff\n"


@pytest.mark.parametrize("automatic", [False, True])
@pytest.mark.parametrize("eol", [b"\n", b"\r\n"])
def test_print_extracts_exact_authored_region_without_refreshing_stale_notes(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, automatic: bool, eol: bytes
) -> None:
    path = stamp(repo)
    region = path.read_bytes().replace(b"main.py", b"main.py  # Keep this note")
    region = region.replace(b"\n", eol).rstrip(b"\r\n")
    path.write_bytes(b"# Intro" + eol + region + eol + b"Other prose" + eol)
    before = path.read_bytes()
    repo.git("rm", "src/main.py")

    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("extracting a saved region must not capture a new Git snapshot")

    monkeypatch.setattr("treestamp.cli_inputs.capture_snapshot", unexpected)
    arguments = ("--print",) if automatic else ("load", str(path), "--print")
    code, output, error = run_cli(*arguments)
    assert code == 0 and not error
    assert output.encode() == region + eol
    assert path.read_bytes() == before


def test_print_load_succeeds_with_an_unmerged_index(repo: Repo) -> None:
    path = stamp(repo)
    before = path.read_bytes()
    one = repo.blob(b"one")
    two = repo.blob(b"two")
    repo.git_bytes(
        "update-index",
        "--index-info",
        input=f"100644 {one} 2\tunmerged\n100644 {two} 3\tunmerged\n".encode(),
    )
    code, output, error = run_cli("load", "--print")
    assert code == 0 and not error and output.encode() == before
    assert run_cli("new", "--print")[0] == 3
    assert path.read_bytes() == before


def test_print_load_does_not_resolve_the_stored_source_root(repo: Repo) -> None:
    path = stamp(repo)
    document, _ = load_document(path)
    assert document is not None
    write_document(replace(document, settings=Settings(root="removed")), path)
    before = path.read_bytes()
    assert not (repo.path / "removed").exists()
    code, output, error = run_cli("load", "--print")
    assert code == 0 and not error and output.encode() == before


def test_new_print_ignores_an_existing_treestamp(repo: Repo) -> None:
    path = stamp(repo)
    before = path.read_bytes()
    repo.write("new.txt")
    repo.add("new.txt")
    code, output, error = run_cli("new", "--print")
    assert code == 0 and not error and "new.txt" in output
    assert path.read_bytes() == before


def test_print_extracts_region_without_a_final_newline(repo: Repo) -> None:
    path = stamp(repo)
    before = path.read_bytes().rstrip(b"\n")
    path.write_bytes(before)
    assert run_cli("load", "--print")[1].encode() == before
