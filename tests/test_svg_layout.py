"""Geometry and display bounds, independent of the metadata transport."""

from dataclasses import replace

import pytest

from treestamp.document import Document
from treestamp.errors import MarkerError
from treestamp.model import Node
from treestamp.svg_layout import (
    CELL,
    INDENT,
    NOTE_COLUMNS,
    PADDING,
    cell_width,
    continuous_layout,
    display_text,
)


def tree() -> Document:
    return Document(
        Node(
            ".",
            "",
            "dir",
            (
                Node(
                    "src",
                    "src",
                    "dir",
                    (Node("file", "src/file", "file"),),
                    annotation="A note " * 20,
                ),
                Node("last", "last", "file"),
            ),
        )
    )


def test_parent_trunk_connects_every_child_and_stops_at_last() -> None:
    layout = continuous_layout(tree())
    labels = {label.text: label for label in layout.labels}
    trunks = [line for line in layout.branches if line.x1 == line.x2]
    arms = [line for line in layout.branches if line.y1 == line.y2]
    assert len(trunks) == 2
    assert len(arms) == 3
    root_trunk = next(line for line in trunks if line.x1 == PADDING + INDENT // 2)
    src_trunk = next(line for line in trunks if line != root_trunk)
    assert root_trunk.y2 == labels["last"].y - 5
    assert src_trunk.y2 == labels["file"].y - 5
    for arm in arms:
        trunk = next(line for line in trunks if line.x1 == arm.x1)
        assert trunk.y1 <= arm.y1 <= trunk.y2
    assert labels["file"].y > labels["src/"].y + 24


def test_long_notes_wrap_without_loss_and_fit_width() -> None:
    note = "界 note " * 100
    document = Document(Node(".", "", "dir", annotation=note))
    layout = continuous_layout(document)
    lines = [label for label in layout.labels if label.role == "note"]
    assert "".join(label.text for label in lines) == note
    assert all(cell_width(label.text) <= NOTE_COLUMNS for label in lines)
    assert all(
        label.x + cell_width(label.text) * CELL < layout.width for label in lines
    )
    assert all(label.y < layout.height for label in lines)


def test_long_names_expand_width_but_are_bounded() -> None:
    name = "n" * 200
    document = Document(Node(".", "", "dir", (Node(name, name, "file"),)))
    assert continuous_layout(document).width > 200 * CELL
    name = "n" * 2000
    document = replace(document, tree=Node(".", "", "dir", (Node(name, name, "file"),)))
    with pytest.raises(MarkerError, match="dimensions"):
        continuous_layout(document)


def test_root_only_layout_is_nonempty_and_attribution_is_visible() -> None:
    document = Document(Node(".", "", "dir"))
    layout = continuous_layout(document)
    assert layout.width >= 240
    assert layout.height > 40
    assert not layout.branches
    document = replace(document, settings=replace(document.settings, attribution=True))
    assert continuous_layout(document).labels[-1].text == "Maintained with treestamp"


def test_width_is_conservative_for_unicode_and_controls_are_visible() -> None:
    assert cell_width("界界") == 4
    assert cell_width("e\u0301") >= 2
    assert display_text("\udc80\x00\u202e\ufffe") == "\\x80\\x00\\u202e\\ufffe"
