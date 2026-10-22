"""Public commands share document updating and expose no authoring flags."""

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from tests.conftest import Repo, run_cli
from treestamp.document import Document, load_document, parse_document, write_document
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings, initial_tree


def stamp(repo: Repo, *, hidden: frozenset[str] = frozenset()) -> Path:
    path = repo.write("README.md", "<!-- treestamp:start -->\n<!-- treestamp:end -->\n")
    repo.write("src/main.py", "original content\n" * 20)
    repo.add(".")
    target = capture_snapshot(repo.path)
    tree = replace(
        target.tree,
        children=tuple(
            node for node in target.tree.children if node.path not in hidden
        ),
    )
    write_document(Document(tree, hidden=hidden), path)
    repo.add("README.md")
    repo.commit()
    return path


@pytest.mark.parametrize("command", [None, "tui", "update", "check"])
@pytest.mark.parametrize(
    "flag",
    [
        "--show-counts",
        "--no-show-counts",
        "--count-mode",
        "--depth",
        "--max-children",
        "--style",
        "--hide-root-files",
        "--no-hide-root-files",
        "--exclude",
        "--hide",
        "--root",
        "--tree-only",
        "--strict",
        "--additions",
        "--moves",
    ],
)
def test_removed_flags_rejected(command: str | None, flag: str) -> None:
    with pytest.raises(SystemExit) as error:
        run_cli(*((command, flag) if command else (flag,)))
    assert error.value.code == 2


@pytest.mark.parametrize("prefix", [(), ("tui",)])
@pytest.mark.parametrize("flag", ["--target", "--compare"])
def test_snapshot_flags_are_maintenance_only(
    prefix: tuple[str, ...], flag: str
) -> None:
    with pytest.raises(SystemExit) as error:
        run_cli(*prefix, flag, "HEAD")
    assert error.value.code == 2


def test_check_update_idempotence_and_unbounded_additions(repo: Repo) -> None:
    path = stamp(repo)
    assert run_cli("check")[0] == 0
    for index in range(30):
        repo.write(f"src/new{index}.py")
    repo.add("src")
    before = path.read_bytes()
    code, out, err = run_cli("check")
    assert code == 1 and "new29.py" in out and not err
    assert path.read_bytes() == before
    assert run_cli("update")[0] == 0
    assert run_cli("check")[0] == 0
    updated = path.read_bytes()
    assert run_cli("update")[0] == 0 and path.read_bytes() == updated


@pytest.mark.parametrize("eol", [b"\n", b"\r\n"], ids=["lf", "crlf"])
def test_formatting_changes_participate_in_check(repo: Repo, eol: bytes) -> None:
    path = stamp(repo)
    baseline = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", eol)
    path.write_bytes(baseline)
    assert run_cli("check")[0] == 0
    original = baseline.replace(
        b"<!-- treestamp:start -->" + eol,
        b"<!-- treestamp:start -->" + eol * 2,
    )
    assert original != baseline
    path.write_bytes(original)
    assert run_cli("check")[0] == 1
    assert path.read_bytes() == original
    assert run_cli("update")[0] == 0
    assert path.read_bytes() != original
    assert run_cli("check")[0] == 0


def test_explicit_hidden_survives_maintenance(repo: Repo) -> None:
    path = stamp(repo, hidden=frozenset({"README.md"}))
    assert run_cli("check")[0] == 0
    document, _ = load_document(path)
    assert document is not None and "README.md" not in {
        n.path for n in document.tree.walk()
    }


@pytest.mark.parametrize("replace_source", [False, True])
def test_comparison_preserves_annotation_and_admits_unrelated_new_paths(
    repo: Repo, replace_source: bool
) -> None:
    path = stamp(repo)
    document, _ = load_document(path)
    assert document is not None
    children = tuple(
        replace(
            node,
            children=tuple(
                replace(child, annotation="entry point") for child in node.children
            ),
        )
        if node.path == "src"
        else node
        for node in document.tree.children
    )
    write_document(
        replace(document, tree=replace(document.tree, children=children)), path
    )
    repo.git("mv", "src/main.py", "src/app.py")
    repo.write("src/new.py")
    repo.add("src/new.py")
    if replace_source:
        repo.write("src/main.py/other")
        repo.add("src/main.py")
    assert run_cli("check", "--compare", "HEAD")[0] == 1
    assert run_cli("update", "--compare", "HEAD")[0] == 0
    document, _ = load_document(path)
    assert document is not None
    nodes = {node.path: node for node in document.tree.walk()}
    assert nodes["src/app.py"].annotation == "entry point"
    assert "src/new.py" in nodes
    assert run_cli("check", "--compare", "HEAD")[0] == 0


@pytest.mark.parametrize("command", ["update", "check"])
def test_bad_comparison_never_writes(repo: Repo, command: str) -> None:
    path = stamp(repo)
    before = path.read_bytes()
    assert run_cli(command, "--compare", "")[0] == 2
    assert run_cli(command, "--compare", "does-not-exist")[0] == 3
    assert path.read_bytes() == before


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
    assert run_cli("--document", str(path.relative_to(repo.path)), "--print")[
        1
    ] == path.read_text(encoding="utf-8")


def test_explicit_ref_ignores_staged_addition(repo: Repo) -> None:
    stamp(repo)
    repo.write("new.txt")
    repo.add("new.txt")
    assert run_cli("check", "--target", "HEAD")[0] == 0
    assert run_cli("check")[0] == 1


@pytest.mark.parametrize("initialized", [False, True])
@pytest.mark.parametrize(
    "arguments",
    [
        ("check",),
        ("update",),
        ("check", "--target", "HEAD"),
        ("update", "--target", "HEAD"),
        ("--print",),
        ("--document", "README.md", "--print"),
    ],
)
def test_document_root_cannot_enter_submodule(
    repo: Repo, initialized: bool, arguments: tuple[str, ...]
) -> None:
    path = stamp(repo)
    repo.git(
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(repo.path),
        "module",
    )
    repo.commit()
    document, _ = load_document(path)
    assert document is not None
    write_document(replace(document, settings=Settings(root="module")), path)
    if not initialized:
        repo.git("submodule", "deinit", "-f", "module")
    before = path.read_bytes()
    code, output, error = run_cli(*arguments)
    assert code == 2 and "selected root is a tracked leaf: 'module'" in error
    assert not output
    assert path.read_bytes() == before


def test_submodule_can_be_selected_as_its_own_repository(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    stamp(repo)
    repo.git(
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(repo.path),
        "module",
    )
    monkeypatch.chdir(repo.path / "module")
    code, output, error = run_cli("check")
    assert code == 0, error or output
    code, output, error = run_cli("--print")
    assert code == 0 and not error and "main.py" in output


@pytest.mark.parametrize("arguments", [["check"], ["--print"], ["tui", "--print"]])
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
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("prefix", [(), ("tui",)])
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


def test_print_open_updates_without_writing_and_preserves_style(repo: Repo) -> None:
    path = stamp(repo)
    document, _ = load_document(path)
    assert document is not None
    repo.write("new.txt")
    repo.add("new.txt")
    for style in ("unicode", "ascii", "list"):
        write_document(replace(document, settings=Settings(style=style)), path)
        before = path.read_bytes()
        code, output, error = run_cli(
            "--document", str(path.relative_to(repo.path)), "--print"
        )
        assert code == 0 and not error and "new.txt" in output
        assert parse_document(output.encode()).settings.style == style
        assert path.read_bytes() == before


def test_default_absent_document_initializes_but_explicit_or_empty_is_error(
    repo: Repo,
) -> None:
    repo.write("app.py")
    repo.add(".")
    assert run_cli("--print")[0] == 0
    assert run_cli("--document", "missing.md", "--print")[0] == 2
    repo.write("README.md", "<!-- treestamp:start -->\n<!-- treestamp:end -->\n")
    assert run_cli("--print")[0] == 2
    repo.write("README.md", "plain prose")
    assert run_cli("--document", "README.md", "--print")[0] == 2


@pytest.mark.parametrize("name", ["render", "fix"])
def test_removed_command_names_can_be_repository_locations(
    repo: Repo, name: str
) -> None:
    repo.write(f"{name}/file")
    repo.add(".")
    assert run_cli(name, "--print")[0] == 0


def test_interactive_open_print_and_write_share_controller(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = stamp(repo)

    def load_then_print(editor, *, startup_document):
        assert editor.state.document_path is None
        assert startup_document == path.relative_to(repo.path)
        editor.adopt(editor.prepare_load(str(startup_document)))
        return True

    monkeypatch.setattr("treestamp.tui.explore", load_then_print)
    code, output, error = run_cli("--document", str(path.relative_to(repo.path)))
    assert code == 0 and output == path.read_text(encoding="utf-8") and not error
    monkeypatch.setattr("treestamp.tui.explore", lambda editor, **kwargs: False)
    assert run_cli("tui", str(repo.path))[1] == ""


def test_cli_reports_io_errors_and_interrupts(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    stamp(repo)

    def fail(*args, **kwargs):
        raise OSError("injected read failure")

    monkeypatch.setattr("treestamp.cli.capture_snapshot", fail)
    code, _, error = run_cli("--print")
    assert code == 3 and "injected read failure" in error

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr("treestamp.cli.capture_snapshot", interrupt)
    assert run_cli("--print")[0] == 130
