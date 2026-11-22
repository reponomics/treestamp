"""Row selection and drawing shared by the tree views."""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from treestamp.codec import format_counts
from treestamp.model import KIND_GITLINK, KIND_SYMLINK

if TYPE_CHECKING:
    from collections.abc import Sequence

    from treestamp.model import Node
    from treestamp.session import TreeSession


@dataclass
class Cursor:
    session: TreeSession
    selected: int = 0

    @property
    def path(self) -> str:
        return self.session.visible_rows()[self.selected][0].path

    def move(self, delta: int) -> None:
        self.selected = min(
            max(0, self.selected + delta), len(self.session.visible_rows()) - 1
        )

    def right(self) -> None:
        rows = self.session.visible_rows()
        node, level = rows[self.selected]
        if not node.is_dir:
            return
        if node.path in self.session.collapsed:
            self.session.expand(node.path)
        elif self.selected + 1 < len(rows) and rows[self.selected + 1][1] > level:
            self.move(1)

    def left(self) -> None:
        rows = self.session.visible_rows()
        node, level = rows[self.selected]
        if node.path and node.children and node.path not in self.session.collapsed:
            self.session.collapse(node.path)
            return
        for index in range(self.selected - 1, -1, -1):
            if rows[index][1] < level:
                self.selected = index
                break

    def toggle(self) -> None:
        node, _ = self.session.visible_rows()[self.selected]
        if node.is_dir and node.path:
            self.session.toggle(node.path)

    def repair(self, path: str) -> None:
        """Keep the selected entry, or the nearest surviving row if it vanished."""
        for index, (node, _) in enumerate(self.session.visible_rows()):
            if node.path == path:
                self.selected = index
                return
        self.move(0)

    def toggle_hidden(self) -> str:
        path = self.path
        if not path:
            return "The root always stays included."
        self.session.toggle_hidden(path)
        self.repair(path)
        if self.session.is_hidden(path):
            return f"Hidden: {path} (H reveals hidden entries)"
        return f"Included: {path}"

    def reveal_hidden(self) -> str:
        path = self.path
        self.session.show_hidden = not self.session.show_hidden
        self.repair(path)
        return (
            "Hidden entries revealed for browsing; output is unchanged."
            if self.session.show_hidden
            else "Hidden entries concealed from this view."
        )

    def show_all(self) -> str:
        path = self.path
        self.session.unhide_all()
        self.repair(path)
        return "All entries included; directory expansion is unchanged."


def label(node: Node) -> str:
    if node.is_dir:
        return f"{node.name}/"
    if node.kind == KIND_GITLINK:
        return f"{node.name}/  # submodule"
    if node.kind == KIND_SYMLINK:
        return f"{node.name} -> {json.dumps(node.target, ensure_ascii=True)}"
    return node.name


def safe_text(text: str) -> str:
    """Keep paths, annotations, and filesystem errors on one safe terminal row."""
    return "".join(
        json.dumps(char, ensure_ascii=True)[1:-1]
        if unicodedata.category(char).startswith("C") or char in "\u2028\u2029"
        else char
        for char in text
    )


def row_label(node: Node, session: TreeSession) -> str:
    closed = node.is_dir and session.is_visibly_collapsed(node.path)
    text = label(node)
    if closed and session.show_counts:
        files, dirs = session.immediate_counts(node.path)
        counts = format_counts(files, dirs)
        if counts:
            text += " " + counts
    annotation = session.annotations.get(node.path, "")
    if annotation:
        text += f"  # {annotation}"
    return ("[hidden] " if session.is_hidden(node.path) else "") + text


def tree_prefixes(rows: Sequence[tuple[Node, int]]) -> list[str]:
    """Return the connector drawn before each row of a depth-first listing."""
    last_children = {
        node.path.rpartition("/")[0]: node.path for node, level in rows if level
    }
    continuations: dict[str, str] = {}
    prefixes: list[str] = []
    for node, level in rows:
        prefix = ""
        continuations[node.path] = ""
        if level:
            parent = node.path.rpartition("/")[0]
            last = last_children[parent] == node.path
            prefix = continuations[parent] + ("└── " if last else "├── ")
            continuations[node.path] = continuations[parent] + (
                "    " if last else "│   "
            )
        prefixes.append(prefix)
    return prefixes
