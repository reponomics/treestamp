"""Records in the Trees API shape build the same trees as the local adapter."""

from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from treestamp import sources
from treestamp.document import Document, prepare_write, render_region
from treestamp.errors import MarkerError
from treestamp.gitio import capture_snapshot
from treestamp.model import KIND_DIR, KIND_FILE, KIND_GITLINK, KIND_SYMLINK, Settings
from treestamp.session import TreeSession
from treestamp.sources import TreeRecord, entries_from_records, tree_from_records

from .conftest import Repo

LINK_ID = "1" * 40
ORPHAN_ID = "2" * 40


def record(
    path: str, mode: str = "100644", type_: str = "blob", object_id: str = "0" * 40
) -> TreeRecord:
    return TreeRecord(path, mode, type_, object_id)


RECORDS = [
    record("src", "040000", "tree"),
    record("src/main.py"),
    record("src/run.sh", "100755"),
    record("link", "120000", "blob", LINK_ID),
    record("orphan", "120000", "blob", ORPHAN_ID),
    record("module", "160000", "commit"),
]


def test_records_map_to_tracked_leaves_with_decoded_targets() -> None:
    tree = tree_from_records(RECORDS, symlink_targets={LINK_ID: b"to\n\t\xff"})
    nodes = {node.path: node for node in tree.walk()}
    assert {path: node.kind for path, node in nodes.items()} == {
        "src": KIND_DIR,
        "src/main.py": KIND_FILE,
        "src/run.sh": KIND_FILE,
        "link": KIND_SYMLINK,
        "orphan": KIND_SYMLINK,
        "module": KIND_GITLINK,
    }
    assert nodes["link"].target == "to\n\t\udcff"
    assert nodes["orphan"].target is None
    assert [child.path for child in tree.children] == [
        "src",
        "link",
        "module",
        "orphan",
    ]
    assert tree_from_records(RECORDS) == tree_from_records(RECORDS, symlink_targets={})


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (record("x", "100664"), "unsupported tree mode"),
        (record("x", "999999"), "unsupported tree mode"),
        (record("x", "100644", "tree"), "disagrees with type"),
        (record("x", "160000", "blob"), "disagrees with type"),
        (record("x", "040000", "blob"), "disagrees with type"),
    ],
)
def test_invalid_records_fail(bad: TreeRecord, message: str) -> None:
    with pytest.raises(MarkerError, match=message):
        entries_from_records([bad])


def test_entry_limit_counts_records_before_scoping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sources, "MAX_ENTRIES", 1)
    with pytest.raises(MarkerError, match="entry limit"):
        entries_from_records([record("a/x"), record("b")], prefix="a/")
    assert [entry.path for entry in entries_from_records([record("a/x")])] == ["a/x"]


def test_prefix_scoping_uses_exact_directory_boundaries() -> None:
    records = [record("src/a"), record("srcfoo/b"), record("other")]
    assert [entry.path for entry in entries_from_records(records, prefix="src/")] == [
        "a"
    ]
    assert entries_from_records(records, prefix="absent/") == []
    with pytest.raises(MarkerError, match="tracked leaf"):
        entries_from_records(records, prefix="other/")


def layout(repo: Repo) -> None:
    # Git trees retain POSIX modes and names even on a Windows host.
    deep = repo.tree([("100644", "blob", repo.blob(b"x"), "leaf.txt")])
    sub = repo.tree(
        [
            ("040000", "tree", deep, "deep"),
            ("100644", "blob", repo.blob(b"y"), "other.txt"),
            ("100755", "blob", repo.blob(b"#!/bin/sh\n"), "run.sh"),
        ]
    )
    entries = [
        ("040000", "tree", sub, "sub"),
        ("100644", "blob", repo.blob(b"z"), "top.txt"),
        ("100644", "blob", repo.blob(b"q"), 'quote "me".txt'),
        ("120000", "blob", repo.blob(b"sub/deep\n\ttarget"), "link"),
    ]
    head = repo.git("commit-tree", repo.tree(entries), "-m", "checkpoint").strip()
    entries.append(("160000", "commit", head, "module"))
    head = repo.git(
        "commit-tree", repo.tree(entries), "-p", head, "-m", "with gitlink"
    ).strip()
    repo.git("update-ref", "HEAD", head)


def git_bytes(repo: Repo, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo.path), "-c", "core.quotePath=false", *args],
        capture_output=True,
        check=True,
    ).stdout


def listing(repo: Repo) -> tuple[list[TreeRecord], dict[str, bytes]]:
    """Records as the Trees API shapes them, including tree rows."""
    records = []
    raw = git_bytes(repo, "ls-tree", "-r", "-t", "-z", "--full-tree", "HEAD")
    for row in raw.split(b"\0"):
        if not row:
            continue
        meta, _, path = row.partition(b"\t")
        mode, type_, object_id = (field.decode("ascii") for field in meta.split())
        records.append(
            TreeRecord(path.decode("utf-8", "surrogateescape"), mode, type_, object_id)
        )
    targets = {
        r.object_id: git_bytes(repo, "cat-file", "blob", r.object_id)
        for r in records
        if r.mode == "120000"
    }
    return records, targets


def test_records_match_local_snapshot_including_scoped_roots(repo: Repo) -> None:
    layout(repo)
    records, targets = listing(repo)
    assert {r.mode for r in records} >= {"040000", "100755", "120000", "160000"}
    assert tree_from_records(records, symlink_targets=targets) == (
        capture_snapshot(repo.path, "HEAD").tree
    )
    assert tree_from_records(records, prefix="sub/", symlink_targets=targets) == (
        capture_snapshot(repo.path / "sub", "HEAD").tree
    )


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_region_from_records_is_byte_identical_to_local_write(
    repo: Repo, style: str
) -> None:
    layout(repo)
    records, targets = listing(repo)
    settings = Settings(style=style)
    hosted = TreeSession(tree_from_records(records, symlink_targets=targets), settings)
    local = TreeSession(capture_snapshot(repo.path, "HEAD").tree, settings)
    for session in (hosted, local):
        session.hide("top.txt")
        session.collapse("sub/deep")
        session.set_annotation("sub", "sources # not a comment")
    documents = [
        Document(s.printed_tree(), s.settings, s.saved_hidden())
        for s in (hosted, local)
    ]
    assert documents[0] == documents[1]
    prepared = prepare_write(documents[1], repo.path / "README.md", create=True)
    region = render_region(documents[0], ".").encode("utf-8", "surrogateescape")
    assert region == prepared.content
    nested = prepare_write(
        replace(documents[1], settings=settings),
        Path(repo.path / "docs" / "README.md"),
        create=True,
    )
    assert render_region(documents[0]).encode() == nested.content
