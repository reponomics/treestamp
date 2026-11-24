"""Pure visual layouts: rows, text runs, and connected branch geometry.

Visual styles operate only on the accepted document projection. Registering a
style changes geometry, never the metadata codec or the shared SVG serializer.
Dimensions use conservative monospace cells; they are not browser font metrics.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

from treestamp.codec import format_counts
from treestamp.errors import MarkerError
from treestamp.model import KIND_GITLINK, KIND_SYMLINK

if TYPE_CHECKING:
    from collections.abc import Callable

    from treestamp.document import Document
    from treestamp.model import Node

CELL = 9
LINE_HEIGHT = 24
INDENT = 30
PADDING = 24
NOTE_COLUMNS = 80
MAX_WIDTH = 16_384
MAX_HEIGHT = 1_000_000


@dataclass(frozen=True)
class TextRun:
    x: int
    y: int
    text: str
    role: str = "file"


@dataclass(frozen=True)
class Segment:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    labels: tuple[TextRun, ...]
    branches: tuple[Segment, ...]


def display_text(value: str) -> str:
    """Make controls, byte names and non-XML characters readable independently."""
    result: list[str] = []
    for char in value:
        code = ord(char)
        if 0xDC80 <= code <= 0xDCFF:
            result.append(f"\\x{code - 0xDC00:02x}")
        elif not char.isprintable() or code in (0xFFFE, 0xFFFF):
            result.append(f"\\u{code:04x}" if code > 255 else f"\\x{code:02x}")
        else:
            result.append(char)
    return "".join(result)


def cell_width(value: str) -> int:
    """Reserve two cells for wide/ambiguous glyphs, one even for combining marks."""
    return sum(2 if unicodedata.east_asian_width(c) in "WFA" else 1 for c in value)


def _wrap_note(value: str) -> tuple[str, ...]:
    """Bound annotation lines without stripping spaces or dropping long tokens."""
    lines: list[str] = []
    current: list[str] = []
    columns = 0
    for char in value:
        width = cell_width(char)
        if columns + width > NOTE_COLUMNS:
            lines.append("".join(current))
            current, columns = [], 0
        current.append(char)
        columns += width
    if current:
        lines.append("".join(current))
    return tuple(lines)


def _label(node: Node) -> str:
    text = display_text(node.name)
    if node.is_dir:
        text += "/"
    elif node.kind == KIND_SYMLINK:
        target = "null" if node.target is None else display_text(node.target)
        text += f" → {target}"
    elif node.kind == KIND_GITLINK:
        text += " [gitlink]"
    counts = format_counts(node.files, node.dirs)
    return f"{text} {counts}" if counts else text


def _row_labels(node: Node, depth: int, baseline: int) -> tuple[list[TextRun], int]:
    x = PADDING + depth * INDENT
    role = "directory" if node.is_dir else "file"
    labels = [TextRun(x, baseline, _label(node), role)]
    notes = _wrap_note(display_text(node.annotation.replace("\t", "  ")))
    # Notes occupy their own indented lines. This keeps the image narrow and
    # avoids connectors intersecting wrapped text or depending on font shaping.
    for offset, note in enumerate(notes, 1):
        labels.append(
            TextRun(x + CELL * 2, baseline + offset * LINE_HEIGHT, note, "note")
        )
    return labels, LINE_HEIGHT * (1 + len(notes))


def continuous_layout(document: Document) -> Layout:
    """Each parent owns one trunk, ending exactly at its last visible child."""
    labels: list[TextRun] = []
    positions: dict[str, tuple[int, int]] = {}
    nodes: list[Node] = []
    stack = [(document.tree, 0)]
    baseline = PADDING + 16
    while stack:
        node, depth = stack.pop()
        row, height = _row_labels(node, depth, baseline)
        labels.extend(row)
        nodes.append(node)
        positions[node.path] = (depth, baseline - 5)
        baseline += height
        stack.extend((child, depth + 1) for child in reversed(node.children))
    branches = _branches(nodes, positions)
    if document.settings.attribution:
        baseline += 8
        labels.append(TextRun(PADDING, baseline, "Maintained with treestamp", "note"))
        baseline += LINE_HEIGHT
    width = max(run.x + cell_width(run.text) * CELL for run in labels) + PADDING
    height = baseline + PADDING - LINE_HEIGHT
    if width > MAX_WIDTH or height > MAX_HEIGHT:
        raise MarkerError("SVG layout exceeds the supported image dimensions")
    return Layout(max(240, width), height, tuple(labels), tuple(branches))


def _branches(
    nodes: list[Node], positions: dict[str, tuple[int, int]]
) -> list[Segment]:
    branches: list[Segment] = []
    for node in nodes:
        if not node.children:
            continue
        depth, parent_y = positions[node.path]
        trunk_x = PADDING + depth * INDENT + INDENT // 2
        last_y = positions[node.children[-1].path][1]
        branches.append(Segment(trunk_x, parent_y + LINE_HEIGHT // 2, trunk_x, last_y))
        for child in node.children:
            child_y = positions[child.path][1]
            branches.append(
                Segment(trunk_x, child_y, trunk_x + INDENT // 2 - 6, child_y)
            )
    return branches


# Internal extension point: styles share static serialization and metadata.
# A test-only second layout proves that adding a style needs no codec changes.
LAYOUT_STYLES: dict[str, Callable[[Document], Layout]] = {
    "continuous": continuous_layout,
}
