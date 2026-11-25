"""Manual review queue and reversible annotation placement."""

import pytest

from treestamp.errors import MarkerError
from treestamp.maintenance import update
from treestamp.model import KIND_SYMLINK, Entry, Settings, build_tree
from treestamp.reconcile import Reconciliation
from treestamp.session import TreeSession


def reconcile(
    before: tuple[str | Entry, ...] = ("old-a", "old-b", "keep"),
    after: tuple[str | Entry, ...] = ("new/a", "new/b", "keep"),
    notes: dict[str, str] | None = None,
) -> Reconciliation:
    def tree(paths: tuple[str | Entry, ...]):
        return build_tree(p if isinstance(p, Entry) else Entry(p) for p in paths)

    old = TreeSession(tree(before), Settings())
    for node in old.root.walk():
        if node.is_dir:
            old.expand(node.path)
    for path, text in (
        {"old-a": "first", "old-b": "second"} if notes is None else notes
    ).items():
        old.set_annotation(path, text)
    loaded = old.printed_tree()
    target = tree(after)
    session = TreeSession(target, Settings(), update(loaded, target, Settings()))
    return Reconciliation(loaded, session)


def test_only_annotated_removed_rows_enter_the_queue() -> None:
    state = reconcile(notes={"old-a": "first", "keep": "survives"})
    assert state.total == state.remaining == 1
    assert state.current is not None and state.current.path == "old-a"
    assert state.session.annotations == {"keep": "survives"}
    assert not state.can_undo


def test_same_path_changed_kind_is_reviewed() -> None:
    state = reconcile(
        ("link",), (Entry("link", KIND_SYMLINK, "target"),), {"link": "note"}
    )
    assert state.total == 1
    state.place("link")
    assert state.session.annotations["link"] == "note"


def test_skip_leaves_the_document_unchanged() -> None:
    state = reconcile()
    before = state.session.state()
    state.skip_current()
    assert state.current is not None and state.current.path == "old-b"
    state.skip_current()
    assert state.current is None and state.remaining == 0
    assert state.skipped == ["old-a", "old-b"]
    assert state.session.state() == before


def test_place_reveals_destination_without_guessing_or_moving_other_rows() -> None:
    state = reconcile()
    state.session.hide("new")
    assert "new" in state.session.collapsed
    state.place("new/b")
    assert state.placed == {"old-a": "new/b"}
    assert state.current is not None and state.current.path == "old-b"
    assert not state.session.is_hidden("new/b")
    assert "new" not in state.session.collapsed
    printed = {
        node.path: node.annotation for node in state.session.printed_tree().walk()
    }
    assert printed["new/b"] == "first" and printed["new/a"] == ""


@pytest.mark.parametrize("source,destination", [("old-a", "new"), ("old", "new/a")])
def test_place_enforces_directory_or_file_sort(source: str, destination: str) -> None:
    state = reconcile(
        before=(source + "/child",) if source == "old" else (source,),
        notes={source: "note"},
    )
    before = state.snapshot(), state.session.state()
    with pytest.raises(MarkerError, match="Choose a"):
        state.place(destination)
    assert (state.snapshot(), state.session.state()) == before


def test_invalid_destination_leaves_queue_unchanged() -> None:
    state = reconcile()
    before = state.snapshot()
    with pytest.raises(MarkerError, match="not a tracked entry"):
        state.place("missing")
    assert state.snapshot() == before


def test_replacement_requires_confirmation_and_undo_restores_it() -> None:
    state = reconcile()
    state.session.set_annotation("new/a", "existing")
    before = state.session.state()
    assert state.conflict("new/a") is not None
    with pytest.raises(MarkerError, match="replace"):
        state.place("new/a")
    state.place("new/a", replace=True)
    assert state.session.annotations["new/a"] == "first"
    assert "old-a" in state.undo()
    assert state.session.state() == before
    assert state.current is not None and state.current.path == "old-a"
    assert not state.placed


def test_identical_existing_annotation_needs_no_replacement_prompt() -> None:
    state = reconcile()
    state.session.set_annotation("new/a", "first")
    assert state.conflict("new/a") is None
    state.place("new/a")
    state.undo()
    assert state.session.annotations["new/a"] == "first"


def test_replacing_a_placed_annotation_returns_its_source_to_review() -> None:
    state = reconcile()
    state.place("new/a")
    before = state.snapshot(), state.session.state()
    assert "old-a" in (state.conflict("new/a") or "")
    state.place("new/a", replace=True)
    assert state.placed == {"old-b": "new/a"}
    assert state.current is not None and state.current.path == "old-a"
    assert state.session.annotations["new/a"] == "second"
    state.undo()
    assert (state.snapshot(), state.session.state()) == before


def test_undo_restores_skips_and_placements_in_order() -> None:
    state = reconcile()
    before = state.session.state()
    state.skip_current()
    state.place("new/b")
    assert state.current is None
    state.undo()
    assert state.current is not None and state.current.path == "old-b"
    state.undo()
    assert state.current is not None and state.current.path == "old-a"
    assert not state.skipped and not state.can_undo
    assert state.session.state() == before
    assert state.undo() == "Nothing to undo."


def test_undo_does_not_overwrite_later_manual_annotation_edits() -> None:
    state = reconcile()
    state.place("new/a")
    state.session.set_annotation("new/a", "edited afterwards")
    state.undo()
    assert state.session.annotations["new/a"] == "edited afterwards"
    assert "new" not in state.session.collapsed
    assert state.current is not None and state.current.path == "old-a"


def test_undo_keeps_subsequent_expansion_and_hiding_decisions() -> None:
    state = reconcile(after=("new/a", "new/b", "other/leaf", "keep"))
    state.session.hide("new")
    state.place("new/a")
    state.session.expand("other")
    state.session.hide("keep")
    state.undo()
    assert "new" not in state.session.collapsed
    assert "other" not in state.session.collapsed
    assert state.session.hidden == {"keep"}
    assert "new/a" not in state.session.annotations


def test_empty_queue_actions_are_safe_or_rejected() -> None:
    state = reconcile(notes={})
    assert state.current is None and state.total == 0
    assert not state.can_undo
    with pytest.raises(MarkerError, match="No note"):
        state.skip_current()
    with pytest.raises(MarkerError, match="No note"):
        state.place("new/a")


def test_unannotated_grandparent_groups_recursive_annotations() -> None:
    state = reconcile(
        before=("old/sub/deep/a", "old/sub/b", "old/c"),
        after=("new/sub/deep/a", "new/sub/b", "new/c"),
        notes={"old/sub/deep/a": "deep", "old/sub": "folder", "old/c": "top"},
    )
    assert state.current is not None and state.current.path == "old"
    assert not state.current.annotation
    assert state.total == state.remaining == state.unplaced == 3
    before = state.snapshot(), state.session.state()
    message = state.place("new")
    assert "3 descendant notes" in message
    assert state.current is None and state.remaining == state.unplaced == 0
    assert state.placed_count == 3
    assert state.session.annotations == {
        "new/sub/deep/a": "deep",
        "new/sub": "folder",
        "new/c": "top",
    }
    assert not {"new", "new/sub", "new/sub/deep"} & state.session.collapsed
    state.undo()
    assert (state.snapshot(), state.session.state()) == before


def test_directory_annotation_and_descendants_are_one_undo_action() -> None:
    state = reconcile(
        before=("old/sub/a", "old/b"),
        after=("new/sub/a", "new/b"),
        notes={"old": "parent", "old/sub/a": "deep", "old/b": "leaf"},
    )
    state.session.hide("new")
    state.session.set_annotation("new", "replaced parent")
    before = state.snapshot(), state.session.state()
    assert state.conflict("new") is not None
    state.place("new", replace=True)
    assert state.placed_count == 3 and state.unplaced == 0
    assert state.session.annotations == {
        "new": "parent",
        "new/sub/a": "deep",
        "new/b": "leaf",
    }
    assert not state.session.is_hidden("new/sub/a")
    state.undo()
    assert (state.snapshot(), state.session.state()) == before


def test_directory_matching_uses_full_relative_path_and_entry_kind() -> None:
    state = reconcile(
        before=("old/input/config", "old/same", "old/missing", "old/type"),
        after=(
            "new/output/config",
            "new/same",
            Entry("new/type", KIND_SYMLINK, "same"),
        ),
        notes={
            "old/input/config": "config",
            "old/same": "match",
            "old/missing": "gone",
            "old/type": "file",
        },
    )
    state.place("new")
    assert state.session.annotations == {"new/same": "match"}
    assert state.placed_count == 1 and state.remaining == 3
    assert state.current is not None and state.current.path == "old/input/config"


def test_directory_carries_identical_text_but_leaves_conflicting_text_pending() -> None:
    state = reconcile(
        before=("old/a", "old/b"),
        after=("new/a", "new/b"),
        notes={"old/a": "same", "old/b": "different"},
    )
    state.session.set_annotation("new/a", "same")
    state.session.set_annotation("new/b", "keep this")
    state.place("new")
    assert state.session.annotations == {"new/a": "same", "new/b": "keep this"}
    assert state.current is not None and state.current.path == "old/b"
    assert state.remaining == 1


def test_directory_does_not_take_destination_held_by_another_source() -> None:
    state = reconcile(
        before=("a/first", "old/a"),
        after=("new/a",),
        notes={"a/first": "same", "old/a": "same"},
    )
    state.skip_current()
    state.place("new/a")
    assert state.current is not None and state.current.path == "old"
    state.place("new")
    assert state.current is not None and state.current.path == "old/a"
    assert state.remaining == 1 and state.placed_count == 1


def test_skipping_a_directory_leaves_its_children_for_manual_placement() -> None:
    state = reconcile(
        before=("old/a", "old/b"),
        after=("new/a", "new/b"),
        notes={"old": "directory", "old/a": "first", "old/b": "second"},
    )
    before = state.session.state()
    state.skip_current()
    assert state.skipped == ["old"]
    assert state.current is not None and state.current.path == "old/a"
    assert state.remaining == 2 and state.unplaced == 3
    state.place("new/b")
    assert state.session.annotations == {"new/b": "first"}
    state.undo()
    state.undo()
    assert state.current is not None and state.current.path == "old"
    assert state.session.state() == before


def test_skipping_unannotated_group_does_not_inflate_skipped_annotations() -> None:
    state = reconcile(
        before=("old/a",),
        after=("new/a",),
        notes={"old/a": "first"},
    )
    state.skip_current()
    assert state.skipped == []
    assert state.current is not None and state.current.path == "old/a"
    assert state.total == state.remaining == state.unplaced == 1


def test_unannotated_group_preserves_existing_destination_annotation() -> None:
    state = reconcile(
        before=("old/a",),
        after=("new/a",),
        notes={"old/a": "first"},
    )
    state.session.set_annotation("new", "keep directory note")
    assert state.conflict("new") is None
    state.place("new")
    assert state.session.annotations == {"new": "keep directory note", "new/a": "first"}


def test_directory_can_place_recursive_children_at_root() -> None:
    state = reconcile(
        before=("old/sub/a",),
        after=("sub/a",),
        notes={"old/sub/a": "deep"},
    )
    state.place("")
    assert state.session.annotations == {"sub/a": "deep"}
    assert state.current is None
