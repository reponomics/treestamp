"""Pure maintenance over a printed tree and complete target facts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from treestamp.errors import MarkerError
from treestamp.model import (
    Node,
    Settings,
    sort_nodes,
    validate_path,
    validate_tree,
    with_counts,
)

if TYPE_CHECKING:
    from collections.abc import Mapping


def _is_hidden(path: str, hidden: frozenset[str]) -> bool:
    parts = path.split("/")
    return any("/".join(parts[:i]) in hidden for i in range(1, len(parts) + 1))


def _move_destination(source: str, destination: str, target: dict[str, Node]) -> Node:
    current = target.get(destination)
    if current is None or current.is_dir:
        raise MarkerError(f"move destination must be a tracked leaf: {destination!r}")
    source_now = target.get(source)
    if source_now is not None and source_now.kind == current.kind:
        raise MarkerError(f"move source remains tracked: {source!r}")
    return current


def _move_annotations(
    moves: Mapping[str, str], original: dict[str, Node], target: dict[str, Node]
) -> dict[str, str]:
    sources, destinations = set(moves), set(moves.values())
    if len(destinations) != len(moves) or sources & destinations:
        raise MarkerError("moves must have unique destinations and disjoint endpoints")
    result = {}
    for source, destination in moves.items():
        validate_path(source)
        validate_path(destination)
        current = _move_destination(source, destination, target)
        old = original.get(source)
        source_now = target.get(source)
        # A repeated update can already print the replacement at the old path.
        if old is None or (source_now is not None and old.kind == source_now.kind):
            continue
        if old.kind != current.kind:
            raise MarkerError(f"move kinds do not match: {source!r} -> {destination!r}")
        result[destination] = old.annotation
    return result


@dataclass(frozen=True)
class _Update:
    settings: Settings
    hidden: frozenset[str]
    annotations: dict[str, str]

    def child(self, target: Node, previous: Node | None) -> Node:
        same = previous is not None and previous.kind == target.kind
        annotation = previous.annotation if same and previous is not None else ""
        if not annotation:
            annotation = self.annotations.get(target.path, "")
        result = replace(
            target, children=(), annotation=annotation, files=None, dirs=None
        )
        if same and previous is not None and previous.is_dir and previous.children:
            result = self.directory(previous, target)
        return with_counts(result, target, self.settings)

    def directory(self, previous: Node, target: Node) -> Node:
        old_children = {child.path: child for child in previous.children}
        children = (
            self.child(child, old_children.get(child.path))
            for child in target.children
            if not _is_hidden(child.path, self.hidden)
        )
        result = replace(
            target,
            children=sort_nodes(children),
            annotation=previous.annotation,
            files=None,
            dirs=None,
        )
        return with_counts(result, target, self.settings)


def update(
    tree: Node,
    target: Node,
    settings: Settings,
    *,
    hidden: frozenset[str] = frozenset(),
    moves: Mapping[str, str] | None = None,
) -> Node:
    """Refresh facts, preserving expansion and admitting all non-hidden children.

    Hidden identities are relative to the selected tree root. Newly admitted
    directories are collapsed. Expansion is read from the original printed tree
    before deleted rows are removed, including when its last child disappears.
    """
    validate_tree(tree)
    validate_tree(target, full=True)
    for path in hidden:
        validate_path(path)
    original = {node.path: node for node in tree.walk()}
    current = {node.path: node for node in target.walk()}
    annotations = _move_annotations(moves or {}, original, current)
    return _Update(settings, hidden, annotations).directory(tree, target)
