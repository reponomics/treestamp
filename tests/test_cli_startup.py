"""Regression coverage for startup command behavior."""

from dataclasses import replace

import pytest

from tests.cli_fixtures import stamp
from tests.conftest import Repo, run_cli
from treestamp.document import Document, load_document, parse_document, write_document
from treestamp.editor import EditorController
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings


@pytest.mark.parametrize("initialized", [False, True])
@pytest.mark.parametrize(
    "arguments",
    [
        ("check",),
        ("update",),
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


def test_interactive_open_print_and_write_share_controller(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = stamp(repo)

    def load_then_print(editor: EditorController) -> bool:
        assert editor.state.document_path == path
        assert editor.state.snapshot.repo == repo.path
        return True

    monkeypatch.setattr("treestamp.tui.explore", load_then_print)
    code, output, error = run_cli("load", str(path.relative_to(repo.path)))
    assert code == 0 and output.encode("utf-8") == path.read_bytes() and not error
    monkeypatch.setattr("treestamp.tui.explore", lambda editor: False)
    assert run_cli("new")[1] == ""


def test_cli_reports_io_errors_and_interrupts(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    stamp(repo)

    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("injected read failure")

    monkeypatch.setattr("treestamp.cli_inputs.capture_snapshot", fail)
    code, _, error = run_cli("new", "--print")
    assert code == 3 and "injected read failure" in error

    def interrupt(*args: object, **kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("treestamp.cli_inputs.capture_snapshot", interrupt)
    assert run_cli("new", "--print")[0] == 130


def test_implicit_and_explicit_documents_both_use_cwd(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = stamp(repo)
    nested = repo.write("docs/README.md", "This is not a treestamp.\n")
    repo.add("docs")
    assert run_cli("update")[0] == 0
    before = path.read_bytes()
    monkeypatch.chdir(nested.parent)
    assert run_cli("check")[0] == 2
    assert run_cli("update")[0] == 2
    generated = parse_document(run_cli("--print")[1].encode())
    assert generated.settings.root == "docs"
    assert run_cli("check", "README.md")[0] == 2
    assert run_cli("load", "README.md", "--print")[0] == 2
    assert run_cli("check", "../README.md")[0] == 0
    assert path.read_bytes() == before
    assert nested.read_text(encoding="utf-8") == "This is not a treestamp.\n"


@pytest.mark.parametrize(
    "source",
    [None, "plain prose", "<!-- treestamp:start -->\n<!-- treestamp:end -->\n"],
)
def test_invalid_explicit_load_fails_before_launching_editor(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, source: str | None
) -> None:
    if source is not None:
        repo.write("README.md", source)

    def unexpected_editor(*args: object, **kwargs: object) -> None:
        pytest.fail("invalid explicit load must fail before launching the TUI")

    monkeypatch.setattr("treestamp.tui.explore", unexpected_editor)
    code, output, error = run_cli("load", "README.md")
    assert code == 2 and error and not output
    if source is not None:
        assert repo.read("README.md") == source


def capture_editor(monkeypatch: pytest.MonkeyPatch) -> list[EditorController]:
    opened: list[EditorController] = []

    def capture(editor: EditorController) -> bool:
        opened.append(editor)
        return False

    monkeypatch.setattr("treestamp.tui.explore", capture)
    return opened


@pytest.mark.parametrize("contents", [None, "ordinary README prose\n"])
def test_bare_startup_creates_at_cwd_without_document_destination(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, contents: str | None
) -> None:
    repo.write("docs/leaf.txt")
    repo.write("outside.txt")
    repo.add(".")
    readme = repo.path / "docs/README.md"
    if contents is not None:
        readme.write_text(contents)
    monkeypatch.chdir(readme.parent)
    opened = capture_editor(monkeypatch)

    assert run_cli() == (0, "", "")
    assert len(opened) == 1
    state = opened[0].state
    assert state.root == readme.parent
    assert state.session.settings.root == "docs"
    assert state.document_path is None
    assert {node.path for node in state.session.root.walk()} == {"leaf.txt"}
    if contents is None:
        assert not readme.exists()
    else:
        assert readme.read_text() == contents


@pytest.mark.parametrize("saved_root", [".", "docs"])
def test_bare_startup_loads_cwd_readme_and_respects_its_saved_root(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, saved_root: str
) -> None:
    repo.write("docs/leaf.txt")
    repo.write("README.md", "unrelated root README")
    repo.add(".")
    path = repo.path / "docs/README.md"
    settings = Settings(root=saved_root)
    write_document(
        Document(capture_snapshot(repo.path / saved_root).tree, settings),
        path,
        create=True,
    )
    before = path.read_bytes()
    repo.write("docs/added.txt")
    repo.add("docs")
    monkeypatch.chdir(path.parent)
    opened = capture_editor(monkeypatch)

    assert run_cli() == (0, "", "")
    state = opened[0].state
    assert state.document_path == path
    assert state.root == repo.path / saved_root
    assert any(node.name == "added.txt" for node in state.session.root.walk())
    assert path.read_bytes() == before


@pytest.mark.parametrize("absolute", [False, True])
def test_new_accepts_directory_without_attaching_document(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, absolute: bool
) -> None:
    file = repo.write("docs/README.md", "<!-- treestamp:start -->broken")
    repo.write("docs/leaf.txt")
    repo.add(".")
    selected = file.parent
    value = str(selected if absolute else selected.relative_to(repo.path))
    opened = capture_editor(monkeypatch)

    assert run_cli("new", value) == (0, "", "")
    assert opened[0].state.root == file.parent
    assert opened[0].state.session.settings.root == "docs"
    assert opened[0].state.document_path is None
    assert not opened[0].state.session.annotations
    assert file.read_text() == "<!-- treestamp:start -->broken"


@pytest.mark.parametrize("absolute", [False, True])
@pytest.mark.parametrize("printing", [False, True])
def test_new_rejects_file_without_opening_editor_or_writing(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, absolute: bool, printing: bool
) -> None:
    path = stamp(repo)
    before = path.read_bytes()
    opened = capture_editor(monkeypatch)
    value = str(path if absolute else path.relative_to(repo.path))
    code, output, error = run_cli("new", value, *(("--print",) if printing else ()))
    assert code == 2 and error and not output
    assert not opened
    assert path.read_bytes() == before


@pytest.mark.parametrize("value", ["missing", "missing.md", "docs/missing.md"])
def test_new_requires_an_existing_source(repo: Repo, value: str) -> None:
    repo.write("docs/leaf")
    repo.add(".")
    code, output, error = run_cli("new", value, "--print")
    assert code == 2 and error and not output


def test_explicit_new_can_select_a_repository_from_outside_git(
    repo: Repo,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    repo.write("leaf")
    repo.add(".")
    monkeypatch.chdir(tmp_path_factory.mktemp("outside-git"))
    for arguments in ((), ("new",), ("load",), ("--print",)):
        code, output, error = run_cli(*arguments)
        assert code == 3 and error and not output
    code, output, error = run_cli("new", str(repo.path), "--print")
    assert code == 0 and not error
    assert {node.path for node in parse_document(output.encode()).tree.walk()} == {
        "leaf"
    }


def test_new_rejects_symlink_before_resolving_parent_components(repo: Repo) -> None:
    repo.write("docs/leaf")
    repo.add(".")
    try:
        (repo.path / "alias").symlink_to(repo.path / "docs", target_is_directory=True)
    except OSError:
        pytest.skip("creating symbolic links is not permitted")
    code, output, error = run_cli("new", "alias/../docs", "--print")
    assert code == 2 and "symbolic link" in error and not output


def test_bare_startup_does_not_hide_broken_readme_by_creating_a_new_tree(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    contents = "<!-- treestamp:start -->\nbroken"
    repo.write("README.md", contents)
    repo.add(".")
    opened = capture_editor(monkeypatch)
    code, output, error = run_cli()
    assert code == 2 and error and not output
    assert not opened
    assert repo.read("README.md") == contents
