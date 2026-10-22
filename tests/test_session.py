"""Saved curation and reversible session state have distinct lifetimes."""

import json
from dataclasses import replace

import pytest

from treestamp.errors import MarkerError
from treestamp.model import Entry, Settings, build_tree
from treestamp.session import SessionState, TreeSession


def make_session(*, expanded: bool = True) -> TreeSession:
    target = build_tree(
        [Entry("src/pkg/leaf"), Entry("src/a"), Entry("src/b"), Entry("readme")]
    )
    session = TreeSession(target, Settings())
    if expanded:
        session.expand("src")
        session.expand("src/pkg")
    return session


def paths(session: TreeSession) -> set[str]:
    return {node.path for node in session.printed_tree().walk()}


def test_collapse_save_expand_restores_hidden_layout_annotations_and_hiding() -> None:
    session = make_session()
    session.hide("src/b")
    session.set_annotation("src/pkg/leaf", "deep annotation")
    original = session.draft_signature()
    session.collapse("src")
    collapsed = session.draft_signature()
    assert session.saved_hidden() == frozenset()
    assert "src/pkg/leaf" not in paths(session)
    assert session.annotations["src/pkg/leaf"] == "deep annotation"
    # Saving reads the serializable state without modifying session internals.
    session.printed_tree()
    session.saved_hidden()
    assert session.draft_signature() == collapsed
    session.expand("src")
    assert session.draft_signature() == original
    assert session.saved_hidden() == frozenset({"src/b"})


def test_reopening_retains_only_printed_rows_and_serialized_hiding() -> None:
    session = make_session()
    session.hide("src/b")
    session.set_annotation("src/pkg/leaf", "hidden annotation")
    session.collapse("src")
    reopened = TreeSession(
        session.root,
        session.settings,
        session.printed_tree(),
        session.saved_hidden(),
    )
    assert not reopened.annotations
    reopened.expand("src")
    assert paths(reopened) == {"src", "src/pkg", "src/a", "src/b", "readme"}
    assert "src/pkg" in reopened.collapsed


def test_loaded_omissions_are_not_inferred_as_hiding() -> None:
    session = make_session()
    original = session.printed_tree()
    src, readme = original.children
    selected = replace(src, children=(src.children[-2],))
    loaded = TreeSession(
        session.root, session.settings, replace(original, children=(selected, readme))
    )
    assert loaded.saved_hidden() == frozenset()
    assert {"src/a", "src/b", "src/pkg"} <= paths(loaded)


@pytest.mark.parametrize("operation", ["collapse", "hide"])
def test_untracked_hiding_follow_printed_parent_lifecycle(operation: str) -> None:
    original = make_session()
    session = TreeSession(
        original.root,
        original.settings,
        original.printed_tree(),
        frozenset({"src/untracked", "untracked"}),
    )
    before = session.draft_signature()
    assert session.saved_hidden() == frozenset({"src/untracked", "untracked"})
    if operation == "collapse":
        session.collapse("src")
    else:
        session.hide("src")
    assert "src/untracked" not in session.saved_hidden()
    assert "untracked" in session.saved_hidden()
    assert "src/untracked" in session.hidden
    if operation == "collapse":
        session.expand("src")
    else:
        session.unhide("src")
    assert session.draft_signature() == before


def test_empty_root_preserves_untracked_hiding() -> None:
    session = TreeSession(build_tree([]), Settings(), hidden=frozenset({"untracked"}))
    assert not session.printed_tree().children
    assert session.saved_hidden() == frozenset({"untracked"})


def test_hidden_edits_and_inspection_do_not_change_saved_signature() -> None:
    session = make_session(expanded=False)
    original = session.draft_signature()
    session.set_annotation("src/a", "session-only")
    session.hide("src/b")
    session.expand("src/pkg")
    session.show_hidden = True
    assert session.draft_signature() == original
    session.expand("src")
    assert session.draft_signature() != original


def test_counts_are_immediate_and_ignore_transient_hiding() -> None:
    session = make_session()
    session.hide("src/a")
    session.hide("src/pkg")
    session.collapse("src")
    src = session.printed_tree().children[0]
    assert (src.files, src.dirs) == (2, 1)
    session.show_counts = False
    assert session.printed_tree().children[0].files is None
    assert session.immediate_counts("src") == (2, 1)


def test_root_remains_expanded_and_can_exclude_all_children() -> None:
    session = make_session()
    session.collapse("")
    session.hide("")
    assert "" not in session.collapsed and "" not in session.hidden
    session.hide("src")
    session.hide("readme")
    assert not session.printed_tree().children
    assert session.saved_hidden() == frozenset({"src", "readme"})


def test_show_descendant_restores_excluded_ancestors() -> None:
    session = make_session()
    session.hide("src")
    session.hide("src/pkg/leaf")
    assert session.is_hidden("src/pkg/leaf")
    session.unhide("src/pkg/leaf")
    assert not session.is_hidden("src/pkg/leaf")


@pytest.mark.parametrize("reveal", [False, True])
def test_show_all_clears_every_hiding_without_changing_layout(reveal: bool) -> None:
    session = make_session()
    session.hide("src")
    session.hide("src/pkg/leaf")
    session.hide("readme")
    session.hidden.add("untracked")
    session.collapse("src/pkg")
    session.set_annotation("src/pkg/leaf", "remember me")
    session.show_hidden = reveal
    before = session.state()

    session.unhide_all()

    assert session.state() == replace(before, hidden=frozenset())
    assert session.show_hidden is reveal
    assert not session.saved_hidden()
    assert paths(session) == {"src", "src/pkg", "src/a", "src/b", "readme"}
    session.expand("src/pkg")
    assert "src/pkg/leaf" in paths(session)
    assert session.annotations["src/pkg/leaf"] == "remember me"
    unchanged = session.state()
    session.unhide_all()
    assert session.state() == unchanged


def test_annotations_support_root_and_validate_without_mutation() -> None:
    session = make_session()
    session.set_annotation(".", "repository")
    assert session.printed_tree().annotation == "repository"
    with pytest.raises(MarkerError, match="single line"):
        session.set_annotation("src", "bad\nannotation")
    assert "src" not in session.annotations
    session.set_annotation("src", ' "quoted"\ttext \t')
    assert session.annotations["src"] == ' "quoted"  text   '
    with pytest.raises(MarkerError, match="single line"):
        session.set_annotation("src", "invalid trailing newline\n")
    assert session.annotations["src"] == ' "quoted"  text   '
    session.set_annotation(".", " ")
    assert session.printed_tree().annotation == " "
    session.set_annotation(".", "")
    assert not session.printed_tree().annotation


def test_root_alias_is_never_visibly_collapsed_even_with_no_printed_children() -> None:
    session = make_session()
    session.hide("src")
    session.hide("readme")
    assert not session.is_visibly_collapsed("")
    assert not session.is_visibly_collapsed(".")


def test_state_round_trip_preserves_transient_curation() -> None:
    session = make_session()
    session.hide("src/b")
    session.set_annotation("src/pkg/leaf", "deep annotation")
    session.set_annotation(".", "root note")
    session.collapse("src")
    state = session.state()
    assert state.expanded == frozenset({"src/pkg"})
    restored = TreeSession.restore(session.root, state)
    assert restored.draft_signature() == session.draft_signature()
    for show_hidden in (False, True):
        session.show_hidden = restored.show_hidden = show_hidden
        assert restored.visible_rows() == session.visible_rows()
    assert restored.state() == state
    assert SessionState.from_dict(json.loads(json.dumps(state.to_dict()))) == state
    for candidate in (session, restored):
        candidate.expand("src")
    assert restored.draft_signature() == session.draft_signature()
    assert restored.saved_hidden() == frozenset({"src/b"})
    assert restored.annotations["src/pkg/leaf"] == "deep annotation"
    assert isinstance(restored.hidden, set) and restored.hidden == {"src/b"}


def test_restore_accepts_untracked_hiding_and_drops_empty_annotations() -> None:
    root = make_session().root
    session = TreeSession(root, Settings(), hidden=frozenset({"src/gone"}))
    session.expand("src")
    assert "src/gone" in session.saved_hidden()
    state = session.state()
    restored = TreeSession.restore(root, replace(state, annotations={"readme": ""}))
    assert "src/gone" in restored.saved_hidden()
    assert restored.annotations == {}
    assert restored.state() == state


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (SessionState(Settings(), frozenset({"absent"}), frozenset(), {}), "directory"),
        (SessionState(Settings(), frozenset({""}), frozenset(), {}), "directory"),
        (SessionState(Settings(), frozenset({"readme"}), frozenset(), {}), "directory"),
        (SessionState(Settings(), frozenset(), frozenset({"../x"}), {}), "invalid"),
        (SessionState(Settings(), frozenset(), frozenset(), {"absent": "x"}), "entry"),
        (
            SessionState(Settings(), frozenset(), frozenset(), {"readme": "a\nb"}),
            "line",
        ),
    ],
)
def test_restore_rejects_inconsistent_state(state: SessionState, message: str) -> None:
    with pytest.raises(MarkerError, match=message):
        TreeSession.restore(make_session().root, state)


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ([], "must be an object"),
        ({"extra": 1}, "unknown session state keys"),
        ({"settings": []}, "settings must be an object"),
        ({"settings": {"bogus": 1}}, "unknown session settings"),
        ({"settings": {"depth": "2"}}, "unknown session settings"),
        ({"expanded": "src"}, "expanded must be an array"),
        ({"hidden": [1]}, "path must be"),
        ({"annotations": [1]}, "record must contain"),
        ({"annotations": {"a": 1}}, "annotations must be an array"),
    ],
)
def test_state_from_dict_rejects_malformed_data(data: object, message: str) -> None:
    with pytest.raises(MarkerError, match=message):
        SessionState.from_dict(data)


def test_state_dict_is_deterministic_and_defaults_missing_keys() -> None:
    first = SessionState(
        Settings(), frozenset("ba"), frozenset("yx"), {"q": "1", "p": "2"}
    )
    second = SessionState(
        Settings(), frozenset("ab"), frozenset("xy"), {"p": "2", "q": "1"}
    )
    assert json.dumps(first.to_dict()) == json.dumps(second.to_dict())
    assert SessionState.from_dict(first.to_dict()) == first
    assert SessionState.from_dict({}) == SessionState(
        Settings(), frozenset(), frozenset(), {}
    )


def test_byte_paths_survive_json_transport() -> None:
    session = TreeSession(build_tree([Entry("dir/byte\udcff")]), Settings())
    session.expand("dir")
    session.hide("dir/byte\udcff")
    session.set_annotation("dir/byte\udcff", "literal note")
    data = session.state().to_dict()
    encoded = json.dumps(data, ensure_ascii=False).encode("utf-8")
    restored = TreeSession.restore(
        session.root, SessionState.from_dict(json.loads(encoded))
    )
    assert restored.state() == session.state()
