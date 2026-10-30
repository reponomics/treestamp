"""Application document paths are rooted in one explicitly selected repository."""

import errno
import os

import pytest

from tests.conftest import Repo, run_cli
from treestamp.document import Document, prepare_write, publish_write, render_region
from treestamp.editor import EditorController
from treestamp.errors import MarkerError
from treestamp.gitio import capture_snapshot, document_path
from treestamp.model import Entry, Settings, build_tree


def editor_for(repo: Repo) -> EditorController:
    repo.write("src/leaf")
    repo.add(".")
    return EditorController(capture_snapshot(repo.path), Settings())


@pytest.mark.parametrize(
    "value",
    [
        "",
        ".",
        "../outside.md",
        "docs/../tree.md",
        "/tree.md",
        "~/tree.md",
        "~user/tree.md",
        "C:/tree.md",
        r"C:\tree.md",
        "C:tree.md",
        r"\\server\share\tree.md",
        r"docs\..\tree.md",
        "bad\x00name",
    ],
)
def test_rejects_nonrelative_or_traversing_document_spelling(
    repo: Repo, value: str
) -> None:
    with pytest.raises(MarkerError):
        document_path(repo.path, value)


def test_inside_absolute_path_is_rejected_without_touching_files(repo: Repo) -> None:
    editor = editor_for(repo)
    editor.create("tree.md")
    before = repo.read_bytes("tree.md")
    for operation in (editor.prepare_load, editor.write, editor.create):
        with pytest.raises(MarkerError, match="relative"):
            operation(str(repo.path / "tree.md"))
    assert repo.read_bytes("tree.md") == before


def test_nested_cwd_and_tree_root_do_not_rebase_document_paths(
    repo: Repo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    editor = editor_for(repo)
    editor.adopt(editor.prepare_new("src"))
    editor.create("./tree.md")
    monkeypatch.chdir(repo.path / "src")
    assert document_path(repo.path, "./tree.md") == repo.path / "tree.md"
    assert run_cli("check", "tree.md")[0] == 2
    assert run_cli("check", "../tree.md")[0] == 0
    assert run_cli("--load", "../tree.md", "--print")[1] == repo.read("tree.md")
    editor.adopt(editor.prepare_load("tree.md"))
    editor.write("tree.md")
    assert not (repo.path / "src" / "tree.md").exists()


@pytest.mark.parametrize("outside_repository", [False, True])
@pytest.mark.parametrize("absolute", [False, True])
def test_explicit_document_selects_its_own_repository(
    repo: Repo,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    outside_repository: bool,
    absolute: bool,
) -> None:
    editor = editor_for(repo)
    editor.create("README.md")
    other = Repo(tmp_path_factory.mktemp("other-repository"))
    other.git("init", "-q")
    other.write("other.txt")
    other.add(".")
    other_editor = EditorController(capture_snapshot(other.path), Settings())
    other_editor.create("README.md")
    if outside_repository:
        monkeypatch.chdir(tmp_path_factory.mktemp("outside-repository"))
    document = other.path / "README.md"
    value = str(document) if absolute else os.path.relpath(document)
    code, output, error = run_cli("--load", value, "--print")
    assert code == 0 and not error and "other.txt" in output and "src/" not in output
    for command in ("check", "update"):
        assert run_cli(command, value)[0] == 0
    assert repo.read("README.md") == editor.region_text()


@pytest.mark.parametrize("link_parent", [False, True])
def test_document_symlinks_are_refused(repo: Repo, link_parent: bool) -> None:
    editor = editor_for(repo)
    editor.create("tree.md")
    try:
        if link_parent:
            (repo.path / "alias").symlink_to(repo.path, target_is_directory=True)
            value = "alias/tree.md"
        else:
            (repo.path / "alias.md").symlink_to("tree.md")
            value = "alias.md"
    except OSError:
        pytest.skip("creating symbolic links is not permitted")
    before = editor.region_text()
    with pytest.raises(MarkerError, match="symbolic link"):
        editor.prepare_load(value)
    with pytest.raises(MarkerError, match="symbolic link"):
        editor.write(value)
    assert editor.region_text() == before and repo.read("tree.md") == before


def test_nested_repository_documents_are_refused(repo: Repo) -> None:
    editor = editor_for(repo)
    nested = Repo(repo.path / "nested")
    nested.path.mkdir()
    nested.git("init", "-q")
    nested.write("tree.md", editor.region_text())
    for operation in (editor.prepare_load, editor.write, editor.create):
        with pytest.raises(MarkerError, match="another repository"):
            operation("nested/tree.md")


@pytest.mark.parametrize("initialized", [False, True])
def test_submodule_documents_are_refused(repo: Repo, initialized: bool) -> None:
    editor = editor_for(repo)
    repo.commit()
    repo.git(
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(repo.path),
        "module",
    )
    if not initialized:
        repo.git("submodule", "deinit", "-f", "module")
    with pytest.raises(MarkerError, match="repository|submodule"):
        editor.create("module/tree.md")
    assert not (repo.path / "module" / "tree.md").exists()


@pytest.mark.parametrize("name", ["notes with spaces.md", " ", "notes\udcff.md"])
def test_document_names_keep_spaces_and_git_bytes(repo: Repo, name: str) -> None:
    if "\udcff" in name and os.name == "nt":
        pytest.skip("Windows filesystem does not support surrogateescaped byte names")
    if name == " " and os.name == "nt":
        pytest.skip("Win32 normalizes whitespace-only path components")
    editor = editor_for(repo)
    assert os.fsencode(document_path(repo.path, name).name) == os.fsencode(name)
    try:
        editor.create(name)
    except OSError as exc:
        if "\udcff" in name and exc.errno == errno.EILSEQ:
            pytest.skip("filesystem rejects non-UTF-8 names")
        raise
    editor.adopt(editor.prepare_load(name))
    editor.write(name)
    assert (repo.path / name).read_text(encoding="utf-8") == editor.region_text()


def test_publication_rechecks_repository_boundary(repo: Repo) -> None:
    repo.write("docs/tree.md", render_region(Document(build_tree([Entry("leaf")]))))
    destination = document_path(repo.path, "docs/tree.md")
    before = destination.read_bytes()
    prepared = prepare_write(
        Document(build_tree([Entry("new")])), destination, repository=repo.path
    )
    Repo(repo.path / "docs").git("init", "-q")
    with pytest.raises(MarkerError, match="another repository"):
        publish_write(prepared)
    assert destination.read_bytes() == before


def test_hidden_unsupported_source_is_still_rejected(repo: Repo) -> None:
    repo.write("nested/a [gitlink]")
    repo.write("keep")
    repo.add(".")
    document = Document(build_tree([Entry("keep")]), hidden=frozenset({"nested"}))
    repo.write("README.md", render_region(document))
    before = repo.read_bytes("README.md")
    for command in ("check", "update"):
        code, output, error = run_cli(command)
        assert code == 2 and not output and "cannot load safely" in error
    assert repo.read_bytes("README.md") == before


@pytest.mark.parametrize("value", ["alias.md", "alias/tree.md", "alias/../tree.md"])
def test_cli_document_symlinks_are_refused_before_normalizing_parents(
    repo: Repo, value: str
) -> None:
    editor = editor_for(repo)
    editor.create("tree.md")
    try:
        (repo.path / "alias.md").symlink_to("tree.md")
        (repo.path / "alias").symlink_to(repo.path / "src", target_is_directory=True)
    except OSError:
        pytest.skip("creating symbolic links is not permitted")
    before = repo.read_bytes("tree.md")
    for arguments in (
        ("--load", value, "--print"),
        ("check", value),
        ("update", value),
    ):
        code, output, error = run_cli(*arguments)
        assert code == 2 and "symbolic link" in error and not output
    assert repo.read_bytes("tree.md") == before


def test_cli_selects_nested_repository_but_editor_does_not_cross_into_it(
    repo: Repo,
) -> None:
    editor = editor_for(repo)
    nested = Repo(repo.path / "nested")
    nested.path.mkdir()
    nested.git("init", "-q")
    nested.write("nested.txt")
    nested.add(".")
    nested_editor = EditorController(capture_snapshot(nested.path), Settings())
    nested_editor.create("tree.md")
    assert run_cli("check", "nested/tree.md")[0] == 0
    code, output, error = run_cli("--load", "nested/tree.md", "--print")
    assert code == 0 and not error and "nested.txt" in output and "src/" not in output
    with pytest.raises(MarkerError, match="another repository"):
        editor.prepare_load("nested/tree.md")


@pytest.mark.parametrize("initialized", [False, True])
def test_cli_submodule_document_ownership(repo: Repo, initialized: bool) -> None:
    editor = editor_for(repo)
    editor.create("tree.md")
    repo.add("tree.md")
    repo.commit()
    repo.git(
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(repo.path),
        "module",
    )
    if not initialized:
        repo.git("submodule", "deinit", "-f", "module")
        # A file under a deinitialized gitlink cannot become a parent-repo document.
        repo.write("module/tree.md", editor.region_text())
    else:
        assert run_cli("update", "module/tree.md")[0] == 0
    for arguments in (
        ("check", "module/tree.md"),
        ("--load", "module/tree.md", "--print"),
    ):
        code, output, error = run_cli(*arguments)
        if initialized:
            assert code == 0 and not error
        else:
            assert code == 2 and "submodule" in error and not output


@pytest.mark.parametrize("value", ["", ".", "bad\x00name", "C:tree.md"])
def test_cli_rejects_invalid_document_path_without_writing(
    repo: Repo, value: str
) -> None:
    editor = editor_for(repo)
    editor.create("tree.md")
    before = repo.read_bytes("tree.md")
    for arguments in (
        ("check", value),
        ("update", value),
        ("--load", value, "--print"),
    ):
        code, output, error = run_cli(*arguments)
        assert code == 2 and error and not output
    assert repo.read_bytes("tree.md") == before
