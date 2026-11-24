"""Automatic updates cannot silently discard notes after source changes."""

from dataclasses import replace
from pathlib import Path

import pytest

from tests.cli_fixtures import stamp
from tests.conftest import Repo, run_cli
from treestamp.document import Document, load_document, write_document
from treestamp.gitio import capture_snapshot
from treestamp.model import Node, Settings, sort_nodes
from treestamp.session import TreeSession


def annotated(
    repo: Repo,
    notes: dict[str, str],
    *,
    collapsed: tuple[str, ...] = (),
    hidden: frozenset[str] = frozenset(),
) -> Path:
    path = stamp(repo)
    document, _ = load_document(path)
    assert document is not None
    session = TreeSession(capture_snapshot(repo.path).tree, Settings(), document.tree)
    for source, note in notes.items():
        session.set_annotation(source, note)
    for directory in collapsed:
        session.collapse(directory)
    write_document(Document(session.printed_tree(), Settings(), hidden), path)
    return path


@pytest.mark.parametrize("kind_change", [False, True])
def test_update_refuses_unmatched_notes_and_override_only_omits_those_notes(
    repo: Repo, kind_change: bool
) -> None:
    notes = {"src/main.py": "keep me", "README.md": "keep me", "": "root note"}
    path = annotated(repo, notes)
    repo.git("rm", "src/main.py")
    if kind_change:
        repo.write("src/main.py/nested.txt")
        repo.add("src")
    before = path.read_bytes()

    code, output, diagnostic = run_cli("update")
    assert code == 2 and not output
    assert "1 unmatched" in diagnostic and "--skip-notes-transfer" in diagnostic
    assert path.read_bytes() == before
    assert not list(repo.path.glob(".treestamp-*"))

    code, diff, diagnostic = run_cli("check")
    assert code == 1 and diff
    assert "1 unmatched" in diagnostic
    assert path.read_bytes() == before

    code, _, diagnostic = run_cli("update", "--skip-notes-transfer")
    assert code == 0 and "1 unmatched" in diagnostic
    saved, _ = load_document(path)
    assert saved is not None
    actual = {
        node.path: node.annotation
        for node in (saved.tree, *saved.tree.walk())
        if node.annotation
    }
    assert actual == {
        key: value for key, value in notes.items() if key != "src/main.py"
    }
    assert run_cli("check")[0] == 0


def test_multiple_missing_notes_are_counted_individually(repo: Repo) -> None:
    path = annotated(repo, {"src": "directory note", "src/main.py": "leaf note"})
    before = path.read_bytes()
    repo.git("rm", "-r", "src")
    code, output, diagnostic = run_cli("update")
    assert code == 2 and not output and "2 unmatched" in diagnostic
    assert path.read_bytes() == before


def test_compare_preserves_a_renamed_note_before_deciding_transfer_is_needed(
    repo: Repo,
) -> None:
    note = "entry point"
    path = annotated(repo, {"src/main.py": note})
    repo.git("mv", "src/main.py", "src/renamed.py")
    before = path.read_bytes()
    assert run_cli("update")[0] == 2
    assert path.read_bytes() == before
    code, _, diagnostic = run_cli("update", "--compare", "HEAD")
    assert code == 0 and not diagnostic
    document, _ = load_document(path)
    assert document is not None
    assert {
        node.path: node.annotation for node in document.tree.walk() if node.annotation
    } == {"src/renamed.py": note}


@pytest.mark.parametrize("hidden", [False, True])
def test_detected_move_does_not_justify_a_note_missing_from_final_output(
    repo: Repo, hidden: bool
) -> None:
    repo.write("destination/keep")
    destination = "destination/renamed.py"
    path = annotated(
        repo,
        {"src/main.py": "source note"},
        collapsed=() if hidden else ("destination",),
        hidden=frozenset({destination}) if hidden else frozenset(),
    )
    repo.git("mv", "src/main.py", destination)
    before = path.read_bytes()
    code, output, diagnostic = run_cli("update", "--compare", "HEAD")
    assert code == 2 and not output and "1 unmatched" in diagnostic
    assert path.read_bytes() == before


def test_conflicting_note_at_detected_move_destination_is_not_silently_replaced(
    repo: Repo,
) -> None:
    path = annotated(repo, {"src/main.py": "source note"})
    document, _ = load_document(path)
    assert document is not None
    destination = "renamed.py"
    # The loaded document can describe a different historical tree from --compare.
    ghost = Node(destination, destination, "file", annotation="destination note")
    tree = replace(document.tree, children=sort_nodes((*document.tree.children, ghost)))
    write_document(replace(document, tree=tree), path)
    repo.git("mv", "src/main.py", destination)
    before = path.read_bytes()

    code, output, diagnostic = run_cli("update", "--compare", "HEAD")
    assert code == 2 and not output and "1 unmatched" in diagnostic
    assert path.read_bytes() == before
    assert run_cli("update", "--compare", "HEAD", "--skip-notes-transfer")[0] == 0
    saved, _ = load_document(path)
    assert saved is not None
    assert (
        next(node for node in saved.tree.walk() if node.path == destination).annotation
        == ghost.annotation
    )
