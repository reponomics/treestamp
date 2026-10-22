"""Shared update preserves curation while admitting all eligible children."""

import random
from dataclasses import replace

import pytest

from treestamp.codec import parse_tree
from treestamp.errors import MarkerError
from treestamp.maintenance import update
from treestamp.model import Entry, Node, Settings, build_tree, initial_tree

S = Settings()


def target(*paths: str) -> Node:
    return build_tree(Entry(path) for path in paths)


def paths(tree: Node) -> list[str]:
    return [node.path for node in tree.walk()]


def test_update_admits_all_siblings_beyond_former_limits() -> None:
    printed = parse_tree(".\n- src/\n  - old  # keep\n")
    current = target(
        "src/old", *[f"src/new{i}" for i in range(50)], *[f"top{i}" for i in range(50)]
    )
    actual = update(printed, current, S)
    assert len(actual.children) == 51
    assert len(actual.children[0].children) == 51
    assert next(n for n in actual.walk() if n.path == "src/old").annotation == "keep"


def test_new_directory_chain_is_collapsed_in_new_and_update() -> None:
    current = target("new/deep/file", "README.md")
    for actual in (initial_tree(current, S), update(target(), current, S)):
        assert paths(actual) == ["new", "README.md"]
        assert (actual.children[0].files, actual.children[0].dirs) == (None, 1)


def test_hidden_paths_block_existing_and_new_children() -> None:
    printed = parse_tree(".\n- src/\n  - a\n  - b\n- hidden/\n")
    actual = update(
        printed,
        target("src/a", "src/b", "hidden/x"),
        S,
        hidden=frozenset({"src/b", "hidden"}),
    )
    assert paths(actual) == ["src", "src/a"]


def test_last_child_replacement_retains_original_expansion() -> None:
    actual = update(
        parse_tree(".\n- src/  # keep\n  - old  # gone\n"), target("src/new"), S
    )
    assert paths(actual) == ["src", "src/new"]
    assert actual.children[0].annotation == "keep"
    assert actual.children[0].children[0].annotation == ""


def test_collapsed_counts_refresh_include_hidden_and_obey_visibility() -> None:
    before = parse_tree(".\n- src/ (90 files)\n")
    after = target("src/a", "src/d/b")
    actual = update(before, after, S, hidden=frozenset({"src/a"}))
    assert paths(actual) == ["src"]
    assert (actual.children[0].files, actual.children[0].dirs) == (1, 1)
    hidden = update(actual, after, replace(S, show_counts=False))
    assert (hidden.children[0].files, hidden.children[0].dirs) == (None, None)


def test_disappeared_subtree_and_empty_repository() -> None:
    assert not update(parse_tree(".\n- gone/\n"), target(), S).children
    with pytest.raises(MarkerError, match="no tracked descendants"):
        update(target(), Node(".", "", "dir", (Node("x", "x", "dir"),)), S)
    with pytest.raises(MarkerError, match="invalid"):
        update(target(), target(), S, hidden=frozenset({"../x"}))


def test_annotation_transfer_and_repeat_update() -> None:
    printed = parse_tree(".\n- old  # entry point\n")
    current = target("new")
    kwargs = dict(moves={"old": "new"})
    actual = update(printed, current, S, **kwargs)
    assert actual.children[0].annotation == "entry point"
    assert update(actual, current, S, **kwargs) == actual


@pytest.mark.parametrize(
    "replacement",
    [Entry("old/other"), Entry("old", "symlink", "new"), Entry("old", "gitlink")],
)
def test_move_replay_preserves_replacement_at_source(replacement: Entry) -> None:
    current = build_tree([Entry("new"), replacement])
    kwargs = dict(moves={"old": "new"})
    actual = update(parse_tree(".\n- old  # moved note\n"), current, S, **kwargs)
    rows = {node.path: node for node in actual.walk()}
    assert rows["new"].annotation == "moved note"
    assert rows["old"].annotation == ""
    curated = replace(
        actual,
        children=tuple(
            replace(node, annotation="replacement note") if node.path == "old" else node
            for node in actual.children
        ),
    )
    assert update(curated, current, S, **kwargs) == curated


@pytest.mark.parametrize(
    "printed", [".\n- old  # note\n- dest/\n", ".\n- old  # note\n"]
)
def test_move_does_not_expand_or_introduce_destination_parent(printed: str) -> None:
    actual = update(
        parse_tree(printed),
        target("dest/new"),
        S,
        moves={"old": "dest/new"},
    )
    assert "dest/new" not in paths(actual)


def test_existing_destination_annotation_wins() -> None:
    printed = parse_tree(".\n- old  # source\n- new  # destination\n")
    actual = update(printed, target("new"), S, moves={"old": "new"})
    assert actual.children[0].annotation == "destination"


def test_move_cannot_override_hiding() -> None:
    printed = parse_tree(".\n- old  # source\n")
    assert not update(
        printed, target("new"), S, hidden=frozenset({"new"}), moves={"old": "new"}
    ).children


def test_kind_replacement_drops_annotation_and_never_expands() -> None:
    printed = parse_tree(".\n- item  # old leaf\n")
    actual = update(printed, target("item/file"), S)
    assert paths(actual) == ["item"]
    assert actual.children[0].annotation == ""
    assert actual.children[0].files == 1


def test_symlink_facts_refresh_without_structural_change() -> None:
    printed = parse_tree('.\n- link -> "old"  # note\n')
    current = build_tree([Entry("link", "symlink", "new")])
    actual = update(printed, current, S)
    assert actual.children[0].target == "new"
    assert actual.children[0].annotation == "note"


@pytest.mark.parametrize(
    "moves",
    [
        {"a": "new", "b": "new"},
        {"a": "b", "b": "new"},
        {"../old": "new"},
        {"a": "absent"},
        {"a": "dir"},
        {"new": "a"},
    ],
)
def test_invalid_move_facts_fail(moves: dict[str, str]) -> None:
    with pytest.raises(MarkerError):
        update(
            parse_tree(".\n- a  # note\n"),
            target("new", "a", "dir/file"),
            S,
            moves=moves,
        )


def test_kind_mismatched_move_fails() -> None:
    with pytest.raises(MarkerError, match="kinds"):
        update(
            parse_tree(".\n- old  # note\n"),
            build_tree([Entry("new", "symlink", "a")]),
            S,
            moves={"old": "new"},
        )


def test_updates_are_idempotent_across_generated_layouts() -> None:
    rng = random.Random(2517)
    pool = [f"d{i}/f{j}" for i in range(4) for j in range(5)]
    for _ in range(40):
        before = target(*rng.sample(pool, 10))
        after = target(*rng.sample(pool, 14))
        layout = replace(
            before,
            children=tuple(
                replace(directory, children=directory.children[: rng.randrange(4)])
                for directory in before.children
            ),
        )
        hidden = frozenset(rng.sample(pool, 3))
        result = update(layout, after, S, hidden=hidden)
        assert update(result, after, S, hidden=hidden) == result
        assert set(paths(result)) <= set(paths(after))
        assert not set(paths(result)) & hidden
