"""Prepare automatic document maintenance and account for every authored note."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from treestamp.artifacts import prepare_artifact_write
from treestamp.document import (
    Document,
    PreparedWrite,
    validate_source_tree,
)
from treestamp.gitio import capture_snapshot
from treestamp.maintenance import update
from treestamp.model import Node, normalize_annotation, tree_path

if TYPE_CHECKING:
    from treestamp.cli_inputs import LoadedSource


def unmatched_notes(previous: Node, updated: Node) -> tuple[str, ...]:
    """Count only notes actually retained in the resulting printed tree."""
    current = {node.path: node for node in (updated, *updated.walk())}
    unmatched = []
    for node in (previous, *previous.walk()):
        if not node.annotation:
            continue
        destination = current.get(node.path)
        if not _retains_note(node, destination):
            unmatched.append(node.path)
    return tuple(unmatched)


def _retains_note(source: Node, destination: Node | None) -> bool:
    return (
        destination is not None
        and destination.kind == source.kind
        and normalize_annotation(destination.annotation)
        == normalize_annotation(source.annotation)
    )


@dataclass(frozen=True)
class Maintenance:
    prepared: PreparedWrite
    unmatched: tuple[str, ...]

    def transfer_notice(self) -> str:
        count = len(self.unmatched)
        noun = "note needs" if count == 1 else "notes need"
        return (
            f"{count} unmatched {noun} transfer; open this document with "
            "'treestamp load DOCUMENT' to transfer notes, or rerun this update "
            "with --skip-notes-transfer to omit them"
        )


def prepare_maintenance(source: LoadedSource) -> Maintenance:
    document, previous = source.document, source.saved
    assert document is not None and previous is not None
    target = capture_snapshot(
        source.repository / document.settings.root,
        repository=source.repository,
    )
    validate_source_tree(target.tree, document.settings)
    hidden = frozenset(
        tree_path(path, document.settings.root) for path in document.hidden
    )
    tree = update(document.tree, target.tree, document.settings, hidden=hidden)
    maintained = Document(tree, document.settings, document.hidden)
    assert source.artifact is not None
    prepared = prepare_artifact_write(
        replace(source.artifact, document=maintained),
        previous.path,
        expected=previous,
        repository=source.repository,
    )
    return Maintenance(prepared, unmatched_notes(document.tree, tree))
