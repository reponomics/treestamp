"""Pure maintenance over a printed tree and complete target facts."""

from __future__ import annotations

from dataclasses import dataclass, replace

from treestamp.model import (
    Node,
    Settings,
    sort_nodes,
    validate_path,
    validate_tree,
    with_counts,
)


def _is_hidden(path: str, hidden: frozenset[str]) -> bool:
    parts = path.split("/")
    return any("/".join(parts[:i]) in hidden for i in range(1, len(parts) + 1))


@dataclass(frozen=True)
class _Update:
    settings: Settings
    hidden: frozenset[str]

    def child(self, target: Node, previous: Node | None) -> Node:
        same = previous is not None and previous.kind == target.kind
        annotation = previous.annotation if same and previous is not None else ""
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
    return _Update(settings, hidden).directory(tree, target)
