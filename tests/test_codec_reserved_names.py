"""Reserved row syntax cannot change a filename's identity or entry kind."""

from dataclasses import replace

import pytest

from treestamp.codec import parse_tree, render_tree, special_paths
from treestamp.document import Document, parse_document, render_region
from treestamp.errors import MarkerError
from treestamp.model import Node, Settings

RESERVED_NAMES = ("odd -> name", "vendor [gitlink]", "raw\udcff\n -> name  # [gitlink]")


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
@pytest.mark.parametrize("root", [".", "source -> root"])
@pytest.mark.parametrize("name", RESERVED_NAMES)
@pytest.mark.parametrize("kind", ["file", "dir", "symlink", "gitlink"])
def test_registered_names_preserve_document_facts(
    style: str, root: str, name: str, kind: str
) -> None:
    child = Node(
        name,
        name,
        kind,
        target="elsewhere -> target\udcfe" if kind == "symlink" else None,
        files=5 if kind == "dir" else None,
        dirs=2 if kind == "dir" else None,
        annotation="note -> target [gitlink]  # still a note",
    )
    document = Document(
        Node(".", "", "dir", children=(child,)),
        Settings(root=root, style=style, attribution=True),
    )
    region = render_region(document).encode()
    assert parse_document(region) == document
    expected_path = name if root == "." else f"{root}/{name}"
    assert special_paths(document.tree, root) == {1: expected_path}


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
@pytest.mark.parametrize("name", RESERVED_NAMES)
def test_reserved_directory_names_scope_children_and_follow_row_changes(
    style: str, name: str
) -> None:
    nested = Node(
        name,
        name,
        "dir",
        children=(
            Node("plain", f"{name}/plain", "file"),
            Node("leaf -> name", f"{name}/leaf -> name", "file"),
        ),
    )
    tree = Node(".", "", "dir", children=(nested,))
    settings = Settings(root="subtree", style=style)
    assert special_paths(tree, settings.root) == {
        1: f"subtree/{name}",
        3: f"subtree/{name}/leaf -> name",
    }
    collapsed = replace(tree, children=(replace(nested, children=(), files=2),))
    assert special_paths(collapsed, settings.root) == {1: f"subtree/{name}"}
    for projection in (tree, collapsed):
        document = Document(projection, settings)
        assert parse_document(render_region(document).encode()) == document


@pytest.mark.parametrize("style", ["unicode", "ascii"])
@pytest.mark.parametrize(
    ("literal", "real"),
    [
        (
            Node("link -> target", "link -> target", "file"),
            Node("link", "link", "symlink", target="target"),
        ),
        (
            Node("module [gitlink]", "module [gitlink]", "file"),
            Node("module", "module", "gitlink"),
        ),
    ],
)
def test_identical_display_heads_keep_literal_and_structural_meanings(
    style: str, literal: Node, real: Node
) -> None:
    for children in ((literal, real), (real, literal)):
        tree = Node(".", "", "dir", children=children)
        text = render_tree(tree, Settings(style=style))
        assert parse_tree(text, style, special_paths=special_paths(tree)) == tree


@pytest.mark.parametrize("name", RESERVED_NAMES)
@pytest.mark.parametrize("suffix", ["extra", " [gitlink]extra", "/junk"])
def test_extended_registration_does_not_bypass_suffix_validation(
    name: str, suffix: str
) -> None:
    tree = Node(".", "", "dir", children=(Node(name, name, "file"),))
    printed = render_tree(tree, Settings()).rstrip("\n") + suffix + "\n"
    with pytest.raises(MarkerError):
        parse_tree(printed, special_paths=special_paths(tree))
