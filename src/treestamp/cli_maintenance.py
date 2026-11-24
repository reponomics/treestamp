"""Prepare automatic document maintenance and account for every authored note."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from treestamp.document import (
    Document,
    PreparedWrite,
    prepare_write,
    validate_source_tree,
)
from treestamp.errors import MarkerError
from treestamp.gitio import capture_snapshot, changes
from treestamp.maintenance import update
from treestamp.model import Node, normalize_annotation, tree_path

if TYPE_CHECKING:
    from collections.abc import Mapping

    from treestamp.cli_inputs import LoadedSource


def unmatched_notes(
    previous: Node, updated: Node, moves: Mapping[str, str]
) -> tuple[str, ...]:
    """Count only notes actually retained in the resulting printed tree."""
    current = {node.path: node for node in (updated, *updated.walk())}
    unmatched = []
    for node in (previous, *previous.walk()):
        if not node.annotation:
            continue
        destination = current.get(node.path)
        if destination is None or destination.kind != node.kind:
            moved = moves.get(node.path)
            destination = current.get(moved) if moved is not None else None
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


def prepare_maintenance(
    source: LoadedSource, target_ref: str | None, comparison_ref: str | None
) -> Maintenance:
    document, previous = source.document, source.saved
    assert document is not None and previous is not None
    if comparison_ref == "":
        raise MarkerError("--compare requires a nonempty ref")
    target = capture_snapshot(
        source.repository / document.settings.root,
        target_ref,
        repository=source.repository,
    )
    validate_source_tree(target.tree, document.settings)
    moves = changes(target, comparison_ref).moves if comparison_ref is not None else {}
    hidden = frozenset(
        tree_path(path, document.settings.root) for path in document.hidden
    )
    tree = update(
        document.tree, target.tree, document.settings, hidden=hidden, moves=moves
    )
    maintained = Document(tree, document.settings, document.hidden)
    prepared = prepare_write(
        maintained, previous.path, expected=previous, repository=source.repository
    )
    return Maintenance(prepared, unmatched_notes(document.tree, tree, moves))
