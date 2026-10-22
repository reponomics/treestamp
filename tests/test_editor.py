"""Fixed-snapshot editor journeys and transactional document writes."""

from dataclasses import replace

import pytest

from treestamp.document import Document, load_document, render_region, write_document
from treestamp.editor import OPEN_UPDATED_NOTICE, EditorController
from treestamp.errors import MarkerError
from treestamp.gitio import capture_snapshot
from treestamp.model import Entry, Settings, build_tree

from .conftest import Repo, run_cli


def make_editor(repo: Repo) -> EditorController:
    for path in ("src/pkg/leaf", "src/a", "src/b", "readme"):
        repo.write(path, path)
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())
    editor.state.session.expand("src")
    editor.state.session.expand("src/pkg")
    return editor


def test_write_collapse_expand_keeps_session_only_curation(repo: Repo) -> None:
    editor = make_editor(repo)
    session = editor.state.session
    session.set_annotation("src/pkg/leaf", "remembered")
    session.hide("src/b")
    original = session.draft_signature()
    session.collapse("src")
    destination = repo.path / "tree.md"
    editor.create(str(destination.relative_to(repo.path)))
    document, _ = load_document(destination)
    assert document is not None and not document.hidden
    assert "remembered" not in destination.read_text(encoding="utf-8")
    session.expand("src")
    assert session.draft_signature() == original
    editor.write(str(destination.relative_to(repo.path)))
    assert "remembered" in destination.read_text(encoding="utf-8")


def test_open_updates_draft_and_notifies_without_writing(repo: Repo) -> None:
    editor = make_editor(repo)
    destination = repo.path / "stale.md"
    stale = build_tree([Entry("src/a"), Entry("obsolete")])
    write_document(Document(stale), destination, create=True)
    before = destination.read_bytes()
    candidate = editor.prepare_load(str(destination.relative_to(repo.path)))
    paths = {node.path for node in candidate.session.printed_tree().walk()}
    assert paths == {"src", "src/a", "src/b", "src/pkg", "readme"}
    assert not candidate.session.saved_hidden()
    assert candidate.status == OPEN_UPDATED_NOTICE
    assert candidate.dirty
    assert editor.state.document_path is None
    assert destination.read_bytes() == before
    editor.adopt(candidate)
    editor.write(str(destination.relative_to(repo.path)))
    assert not editor.dirty
    reopened = editor.prepare_load(str(destination.relative_to(repo.path)))
    assert reopened.status == "Treestamp is up to date"
    assert not reopened.dirty


def test_open_captures_new_index_then_edits_use_fixed_snapshot(repo: Repo) -> None:
    editor = make_editor(repo)
    destination = repo.path / "tree.md"
    editor.create(str(destination.relative_to(repo.path)))
    repo.write("src/new")
    repo.add("src/new")
    candidate = editor.prepare_load(str(destination.relative_to(repo.path)))
    assert candidate.snapshot.tree_id != editor.state.snapshot.tree_id
    editor.adopt(candidate)
    assert "src/new" in {node.path for node in candidate.session.printed_tree().walk()}
    before = editor.region_text()
    repo.git("rm", "-f", "src/a")
    repo.write("src/later")
    repo.add("src/later")
    candidate.session.collapse("src")
    candidate.session.expand("src")
    assert editor.region_text() == before
    editor.write(str(destination.relative_to(repo.path)))
    assert "later" not in destination.read_text(encoding="utf-8")
    assert "├── a" in destination.read_text(encoding="utf-8")


def test_hidden_absent_path_survives_update_and_retracking(repo: Repo) -> None:
    editor = make_editor(repo)
    editor.state.session.hide("src/b")
    destination = repo.path / "tree.md"
    editor.create(str(destination.relative_to(repo.path)))
    repo.git("rm", "--cached", "src/b")
    assert run_cli("update", str(destination.relative_to(repo.path)))[0] == 0
    editor.adopt(editor.prepare_load(str(destination.relative_to(repo.path))))
    assert editor.state.session.saved_hidden() == frozenset({"src/b"})
    before = destination.read_bytes()
    editor.write(str(destination.relative_to(repo.path)))
    assert destination.read_bytes() == before
    repo.add("src/b")
    assert run_cli("update", str(destination.relative_to(repo.path)))[0] == 0
    document, _ = load_document(destination)
    assert document is not None and document.hidden == frozenset({"src/b"})
    assert "src/b" not in {node.path for node in document.tree.walk()}


def test_failed_load_and_conflicting_write_preserve_draft(repo: Repo) -> None:
    editor = make_editor(repo)
    destination = repo.path / "tree.md"
    editor.create(str(destination.relative_to(repo.path)))
    editor.state.session.set_annotation("src", "unwritten")
    state = editor.state
    signature = state.session.draft_signature()
    destination.write_text("concurrent edit\n", encoding="utf-8")
    with pytest.raises(MarkerError):
        editor.write(str(destination.relative_to(repo.path)))
    with pytest.raises(MarkerError):
        editor.prepare_load(str(destination.relative_to(repo.path)))
    assert editor.state is state
    assert state.session.draft_signature() == signature
    assert destination.read_text(encoding="utf-8") == "concurrent edit\n"


def test_document_location_does_not_rebase_root_or_hidden(repo: Repo) -> None:
    editor = make_editor(repo)
    editor.adopt(editor.prepare_new("src"))
    editor.state.session.hide("b")
    destination = repo.write(
        "docs/map.md",
        "Before\n<!-- treestamp:start -->\nold junk\n<!-- treestamp:end -->\nAfter\n",
    )
    editor.write(str(destination.relative_to(repo.path)))
    document, _ = load_document(destination)
    assert document is not None and document.settings.root == "src"
    assert document.hidden == frozenset({"src/b"})
    assert destination.read_text(encoding="utf-8").startswith("Before\n")
    assert destination.read_text(encoding="utf-8").endswith("After\n")
    assert editor.region_text() == render_region(document)
    reopened = editor.prepare_load(str(destination.relative_to(repo.path)))
    assert reopened.root == repo.path / "src"
    with pytest.raises(MarkerError):
        editor.create(str(destination.relative_to(repo.path)))
    with pytest.raises(MarkerError):
        editor.prepare_new("../outside")


@pytest.mark.parametrize("operation", ["open", "new"])
def test_root_selection_cannot_enter_initialized_submodule(
    repo: Repo, operation: str
) -> None:
    editor = make_editor(repo)
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
    destination = repo.path / "tree.md"
    write_document(
        Document(build_tree([Entry("src/a")]), Settings(root="module")),
        destination,
        create=True,
    )
    state = editor.state
    with pytest.raises(MarkerError, match="selected root is a tracked leaf"):
        if operation == "open":
            editor.prepare_load(str(destination.relative_to(repo.path)))
        else:
            editor.prepare_new("module")
    assert editor.state is state


def test_noncanonical_open_is_dirty_even_when_semantics_unchanged(repo: Repo) -> None:
    editor = make_editor(repo)
    destination = repo.path / "tree.md"
    editor.create(str(destination.relative_to(repo.path)))
    destination.write_bytes(
        destination.read_bytes().replace(
            b"<!-- treestamp:start -->\n", b"<!-- treestamp:start -->\n\n"
        )
    )
    before = destination.read_bytes()
    candidate = editor.prepare_load(str(destination.relative_to(repo.path)))
    assert candidate.status == OPEN_UPDATED_NOTICE
    assert candidate.dirty
    assert destination.read_bytes() == before


def test_special_paths_derive_from_printed_entries(repo: Repo) -> None:
    repo.write("docs  # drafts/notes  # draft.md")
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())
    session = editor.state.session
    session.expand("docs  # drafts")
    session.set_annotation("docs  # drafts/notes  # draft.md", "Keep # and ##")
    expanded = editor.region_text()
    assert '"docs  # drafts/notes  # draft.md"' in expanded
    session.collapse("docs  # drafts")
    assert '"docs  # drafts/notes  # draft.md"' not in editor.region_text()
    session.expand("docs  # drafts")
    assert editor.region_text() == expanded
    session.hide("docs  # drafts")
    assert "special_paths" not in editor.region_text()


@pytest.mark.parametrize("changed", ["count", "target"])
def test_counts_and_symlink_changes_are_noticed(repo: Repo, changed: str) -> None:
    from treestamp.gitio import Snapshot

    tree = build_tree(
        [Entry("src/a"), Entry("src/b"), Entry("shortcut", "symlink", "new")]
    )
    snapshot = Snapshot(repo.path, repo.path, tree, "fixed")
    original = EditorController(snapshot, Settings()).document()
    src, shortcut = original.tree.children
    if changed == "count":
        src = replace(src, files=1)
    else:
        shortcut = replace(shortcut, target="old")
    original = replace(original, tree=replace(original.tree, children=(src, shortcut)))
    editor = EditorController(snapshot, Settings(), loaded_document=original)
    assert editor.state.status == OPEN_UPDATED_NOTICE


def test_dirty_uses_output_for_count_and_root_only_style_choices(repo: Repo) -> None:
    repo.write("leaf")
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())
    assert not editor.dirty
    editor.state.session.show_counts = False
    assert not editor.dirty, "counts have no printed effect when no folder is collapsed"
    destination = repo.path / "tree.md"
    editor.create(str(destination.relative_to(repo.path)))
    editor.state.session.show_counts = True
    assert not editor.dirty
    assert editor.state.baseline is editor.state.document_snapshot

    empty = EditorController(
        replace(editor.state.snapshot, tree=build_tree([])), Settings()
    )
    empty.state.session.settings = replace(empty.state.session.settings, style="ascii")
    assert not empty.dirty, "root-only ASCII and Unicode print the same bytes"
    empty.state.session.settings = replace(empty.state.session.settings, style="list")
    assert empty.dirty
    empty.state.session.settings = replace(
        empty.state.session.settings, style="unicode"
    )
    assert not empty.dirty


def test_dirty_tracks_restoring_original_bytes_after_a_changed_open(repo: Repo) -> None:
    repo.write("src/leaf")
    repo.add(".")
    snapshot = capture_snapshot(repo.path)
    original_editor = EditorController(snapshot, Settings(show_counts=False))
    destination = repo.path / "tree.md"
    original_editor.create(str(destination.relative_to(repo.path)))
    # Keep the original CRLF bytes and unrelated document content as the baseline.
    destination.write_bytes(
        b"Before\r\n" + destination.read_bytes().replace(b"\n", b"\r\n") + b"After\r\n"
    )
    original, saved = load_document(destination)
    assert original is not None and saved is not None
    editor = EditorController(
        snapshot,
        Settings(),
        loaded_document=original,
        document_snapshot=saved,
        document_path=destination,
    )
    assert editor.dirty and editor.state.status == OPEN_UPDATED_NOTICE
    editor.state.session.show_counts = False
    assert not editor.dirty, "restoring the original output clears unwritten state"
    editor.state.session.show_counts = True
    assert editor.dirty
    assert destination.read_bytes() == saved.content


@pytest.mark.parametrize("name", ["a [gitlink]", "nested/a [gitlink]"])
def test_initial_unrepresentable_source_is_rejected(repo: Repo, name: str) -> None:
    repo.write(name)
    repo.add(".")
    with pytest.raises(MarkerError, match="cannot load safely"):
        EditorController(capture_snapshot(repo.path), Settings())


def test_failed_source_preflight_preserves_loaded_draft(repo: Repo) -> None:
    editor = make_editor(repo)
    editor.create("tree.md")
    before = editor.region_text()
    state = editor.state
    repo.write("src/pkg/a [gitlink]")
    repo.add(".")
    with pytest.raises(MarkerError, match="cannot load safely"):
        editor.prepare_load("tree.md")
    assert editor.state is state and editor.region_text() == before
    assert repo.read("tree.md") == before


def test_candidate_annotation_rolls_back_complete_session(repo: Repo) -> None:
    repo.write("x")
    repo.write("x  # y")
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())
    session = editor.state.session
    before = editor.region_text()
    with pytest.raises(MarkerError, match="ambiguous special-path"), editor.edit():
        session.set_annotation("x", "y")
    assert editor.region_text() == before and not session.annotations


def test_preflight_only_checks_selected_subtree(repo: Repo) -> None:
    repo.write("good/leaf")
    repo.write("other/a [gitlink]")
    repo.add(".")
    snapshot = capture_snapshot(repo.path / "good", repository=repo.path)
    editor = EditorController(snapshot, Settings(root="good"))
    editor.create("tree.md")
    assert "leaf" in repo.read("tree.md")
