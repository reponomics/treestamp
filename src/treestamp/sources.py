"""Tree facts from records not produced by a local git invocation.

The GitHub Trees API and ``git ls-tree`` describe the same objects. This
module maps those records onto tracked leaves so a hosted caller can build a
target tree without a checkout or a ``git`` binary. Failures here are invalid
input (exit 2); the local adapter in ``gitio`` keeps its environment errors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from treestamp.errors import MarkerError
from treestamp.model import (
    KIND_DIR,
    KIND_FILE,
    KIND_GITLINK,
    KIND_SYMLINK,
    Entry,
    Node,
    build_tree,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

MAX_ENTRIES = 200_000
MODE_KINDS: Mapping[str, str] = {
    "100644": KIND_FILE,
    "100755": KIND_FILE,
    "120000": KIND_SYMLINK,
    "160000": KIND_GITLINK,
    "040000": KIND_DIR,
}
MODE_TYPES: Mapping[str, str] = {
    "100644": "blob",
    "100755": "blob",
    "120000": "blob",
    "160000": "commit",
    "040000": "tree",
}


@dataclass(frozen=True)
class TreeRecord:
    """One row of a recursive tree listing, in the Trees API field shape."""

    path: str
    mode: str
    type: str
    object_id: str


def _leaf_kind(record: TreeRecord) -> str | None:
    kind = MODE_KINDS.get(record.mode)
    if kind is None:
        raise MarkerError(f"unsupported tree mode {record.mode!r}: {record.path!r}")
    if MODE_TYPES[record.mode] != record.type:
        raise MarkerError(
            f"tree mode {record.mode!r} disagrees with type {record.type!r}: "
            f"{record.path!r}"
        )
    return None if kind == KIND_DIR else kind


def entries_from_records(
    records: Iterable[TreeRecord],
    *,
    prefix: str = "",
    symlink_targets: Mapping[str, bytes] | None = None,
) -> list[Entry]:
    """Map records to tracked leaves beneath prefix; decode targets like gitio."""
    rows = list(records)
    if len(rows) > MAX_ENTRIES:
        raise MarkerError("tree exceeds the collection entry limit")
    entries: list[Entry] = []
    for record in rows:
        kind = _leaf_kind(record)
        if prefix and record.path == prefix.rstrip("/") and kind is not None:
            raise MarkerError(f"selected root is a tracked leaf: {record.path!r}")
        if kind is None or not record.path.startswith(prefix):
            continue
        path = record.path[len(prefix) :]
        target = None
        if kind == KIND_SYMLINK and symlink_targets is not None:
            raw = symlink_targets.get(record.object_id)
            if raw is not None:
                target = raw.decode("utf-8", "surrogateescape")
        entries.append(Entry(path, kind, target=target))
    return entries


def tree_from_records(
    records: Iterable[TreeRecord],
    *,
    prefix: str = "",
    symlink_targets: Mapping[str, bytes] | None = None,
) -> Node:
    """Build the complete target tree beneath prefix."""
    return build_tree(
        entries_from_records(records, prefix=prefix, symlink_targets=symlink_targets)
    )
