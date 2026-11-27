"""Generated curation: rejected edits, JSON transport, and restored behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass

from hypothesis import given
from hypothesis import strategies as st

from treestamp.errors import MarkerError
from treestamp.model import (
    KIND_FILE,
    KIND_GITLINK,
    KIND_SYMLINK,
    Entry,
    Node,
    Settings,
    build_tree,
)
from treestamp.session import SessionState, TreeSession

from .property_strategies import annotation_texts, names, symlink_targets


@st.composite
def _tracked_leaves(draw: st.DrawFn, prefix: str, depth: int) -> list[Entry]:
    entries: list[Entry] = []
    for name in draw(st.lists(names, min_size=1, max_size=3, unique=True)):
        path = f"{prefix}/{name}" if prefix else name
        if depth and draw(st.booleans()):
            entries += draw(_tracked_leaves(path, depth - 1))
            continue
        kind = draw(st.sampled_from((KIND_FILE, KIND_SYMLINK, KIND_GITLINK)))
        target = draw(symlink_targets) if kind == KIND_SYMLINK else None
        entries.append(Entry(path, kind, target))
    return entries


targets = _tracked_leaves("", 2).map(build_tree)

OPERATIONS = (
    "toggle",
    "expand",
    "collapse",
    "hide",
    "unhide",
    "unhide_all",
    "annotate",
    "counts",
)


@dataclass(frozen=True)
class Operation:
    kind: str
    path: str
    text: str = ""

    def apply(self, session: TreeSession) -> None:
        if self.kind == "annotate":
            session.set_annotation(self.path, self.text)
        elif self.kind == "unhide_all":
            session.unhide_all()
        elif self.kind == "counts":
            session.show_counts = not session.show_counts
        else:
            getattr(session, self.kind)(self.path)


def operations(target_paths: list[str]) -> st.SearchStrategy[list[Operation]]:
    paths = st.one_of(st.sampled_from([*target_paths, "."]), names)
    operation = st.builds(
        Operation, st.sampled_from(OPERATIONS), paths, annotation_texts
    )
    return st.lists(operation, max_size=12)


def observable(session: TreeSession) -> tuple[object, ...]:
    rows = []
    for reveal in (False, True):
        session.show_hidden = reveal
        rows.append([(node.path, depth) for node, depth in session.visible_rows()])
    session.show_hidden = False
    paths = [node.path for node in session.root.walk()]
    directories = [node.path for node in session.root.walk() if node.is_dir]
    return (
        session.state(),
        session.printed_tree(),
        session.saved_hidden(),
        session.hidden_stats(),
        rows,
        [session.is_hidden(path) for path in paths],
        [session.is_visibly_collapsed(path) for path in directories],
    )


def transported(session: TreeSession) -> TreeSession:
    wire = json.dumps(session.state().to_dict())
    restored = TreeSession.restore(
        session.root, SessionState.from_dict(json.loads(wire))
    )
    assert json.dumps(restored.state().to_dict()) == wire
    return restored


def _apply_or_reject(session: TreeSession, operation: Operation) -> bool:
    before = observable(session)
    try:
        operation.apply(session)
    except MarkerError:
        assert observable(session) == before, "a rejected edit changed the session"
        return False
    return True


def _with_operations(
    target: Node,
) -> st.SearchStrategy[tuple[Node, list[Operation], list[Operation]]]:
    paths = [node.path for node in (target, *target.walk())]
    return st.tuples(st.just(target), operations(paths), operations(paths))


@given(targets.flatmap(_with_operations))
def test_transport_preserves_curation_and_later_behavior(
    case: tuple[Node, list[Operation], list[Operation]],
) -> None:
    target, before, after = case
    session = TreeSession(target, Settings())
    for operation in before:
        _apply_or_reject(session, operation)
    restored = transported(session)
    assert observable(restored) == observable(session)
    for operation in after:
        assert _apply_or_reject(session, operation) == _apply_or_reject(
            restored, operation
        )
        assert observable(restored) == observable(session)


@st.composite
def captured_states(draw: st.DrawFn) -> tuple[Node, SessionState]:
    target = draw(targets)
    tracked = [node for node in target.walk()]
    directories = [node.path for node in tracked if node.is_dir]
    expanded = draw(st.sets(st.sampled_from(directories))) if directories else set()
    hidden = draw(
        st.sets(
            st.one_of(st.sampled_from([n.path for n in tracked]), names), max_size=4
        )
    )
    annotated = draw(
        st.dictionaries(
            st.sampled_from(["", *[n.path for n in tracked]]),
            annotation_texts,
            max_size=4,
        )
    )
    settings = Settings(
        show_counts=draw(st.booleans()),
        style=draw(st.sampled_from(("unicode", "ascii"))),
    )
    return target, SessionState(
        settings, frozenset(expanded), frozenset(hidden), annotated
    )


@given(captured_states())
def test_restore_applies_only_specified_normalization(
    case: tuple[Node, SessionState],
) -> None:
    target, state = case
    restored = TreeSession.restore(
        target, SessionState.from_dict(json.loads(json.dumps(state.to_dict())))
    )
    expected_notes = {
        path: text.replace("\t", "  ")
        for path, text in state.annotations.items()
        if text
    }
    assert restored.state() == SessionState(
        state.settings, state.expanded, state.hidden, expected_notes
    )
