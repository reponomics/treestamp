"""Print and read tree rows without repository access.

Names remain literal except for control/byte escapes and list-style Markdown.
A fixed delimiter separates annotations. Exceptional full path registrations
resolve names containing that delimiter before interpreting row suffixes.
Before returning output, check
that parsing preserves the authored paths, kinds, structure, and annotations.
Counts and targets are regenerated facts, not saved curation.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING

from treestamp.errors import MarkerError
from treestamp.model import (
    ANNOTATION_DELIMITER,
    KIND_DIR,
    KIND_FILE,
    KIND_GITLINK,
    KIND_SYMLINK,
    Node,
    Settings,
    normalize_annotation,
    repo_path,
    tree_path,
    validate_tree,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

SYMLINK_ARROW = "->"
GITLINK_TAG = "[gitlink]"

# A row is one line, so control characters print as C escapes, and a byte that
# is not UTF-8 (a surrogate, from decoding with "surrogateescape") prints as its
# hex value. The backslash is escaped as well, which makes the mapping reversible.
_CONTROL = re.compile(r"[\\\x00-\x1f\x7f-\x9f\u2028\u2029\udc80-\udcff]")
_NAMED_ESCAPES = {"\\": "\\\\", "\n": "\\n", "\t": "\\t", "\r": "\\r"}
_NAMED_CHARACTERS = {sequence: char for char, sequence in _NAMED_ESCAPES.items()}
_ESCAPE = re.compile(r"\\(?:[\\ntr]|x[0-9a-f]{2}|u[0-9a-f]{4})")

# What can begin a Markdown construct where a list row's name sits. A backslash
# before any of these renders the character itself, so an escaped name shows the
# name. Only list rows are escaped; fenced rows are already inert. Underscore is
# absent on purpose: CommonMark does not emphasise intraword underscores, and
# escaping every test_thing.py would cost more legibility than it buys; an
# underscore that is not intraword, as in a file named _draft_, still is. The
# backslash is in the set so that escaping is reversible. A few characters start
# a block only at the beginning of the item: a heading, a list, a blockquote.
_MARKDOWN = re.compile(r"[`*\[\]<>&~\\]|(?<![0-9A-Za-z])_|_(?![0-9A-Za-z])")
_MARKDOWN_BLOCK = re.compile(r"\A(?:[#+-]|\d{1,9}[.)])(?= |\Z)|\A>")
_MARKDOWN_ESCAPED = re.compile(r"\\([!-/:-@\[-`{-~])")

_COUNT = re.compile(r" \((\d+) (files?|folders?)(?:, (\d+) folders?)?\)")


def _escape(text: str) -> str:
    def character(match: re.Match[str]) -> str:
        if match[0] in _NAMED_ESCAPES:
            return _NAMED_ESCAPES[match[0]]
        value = ord(match[0])
        if value < 0x80 or 0xDC80 <= value <= 0xDCFF:
            return f"\\x{value & 0xFF:02x}"
        return f"\\u{value:04x}"

    return _CONTROL.sub(character, text)


def _unescape(text: str) -> str:
    def character(match: re.Match[str]) -> str:
        sequence = match[0]
        if sequence in _NAMED_CHARACTERS:
            return _NAMED_CHARACTERS[sequence]
        value = int(sequence[2:], 16)
        if sequence.startswith("\\u"):
            return chr(value)
        return chr(value if value < 0x80 else 0xDC00 + value)

    return _ESCAPE.sub(character, text)


def _markdown(text: str) -> str:
    text = _MARKDOWN.sub(lambda match: "\\" + match[0], text)
    block = _MARKDOWN_BLOCK.match(text)
    if block:
        last = block.end() - 1
        text = text[:last] + "\\" + text[last:]
    return text


def _display(text: str, markdown: bool) -> str:
    """Print a name or target: escaped onto one line, and inert in Markdown."""
    trailing = len(text) - len(text.rstrip())
    body = text[:-trailing] if trailing else text
    suffix = text[-trailing:] if trailing else ""
    text = _escape(body) + "".join(
        f"\\x{ord(char):02x}" if ord(char) < 128 else f"\\u{ord(char):04x}"
        for char in suffix
    )
    return _markdown(text) if markdown else text


def _read(text: str, markdown: bool) -> str:
    if markdown:
        text = _MARKDOWN_ESCAPED.sub(r"\1", text)
    return _unescape(text)


def format_counts(files: int | None, dirs: int | None) -> str:
    """``(N files, M folders)`` with absent and zero parts omitted; "" if none."""
    parts = []
    if files:
        parts.append(f"{files} file{'' if files == 1 else 's'}")
    if dirs:
        parts.append(f"{dirs} folder{'' if dirs == 1 else 's'}")
    return f"({', '.join(parts)})" if parts else ""


def _row_head(node: Node, *, markdown: bool = False) -> str:
    text = "." if not node.path else _display(node.name, markdown)
    if node.is_dir:
        text += "/"
    elif node.kind == KIND_GITLINK:
        text += f" {GITLINK_TAG}"
    elif node.kind == KIND_SYMLINK:
        target = "null" if node.target is None else _display(node.target, markdown)
        text += f" {SYMLINK_ARROW} {target}"
    counts = format_counts(node.files, node.dirs)
    if counts:
        text += " " + counts
    return text


def special_paths(tree: Node, root: str = ".") -> dict[int, str]:
    """Map printed row indices to exact repository-relative special identities."""
    return {
        row: repo_path(node.path, root)
        for row, node in enumerate(tree.walk(), 1)
        if ANNOTATION_DELIMITER in node.name
    }


def _row(node: Node, *, markdown: bool = False) -> str:
    text = _row_head(node, markdown=markdown)
    annotation = normalize_annotation(node.annotation)
    if annotation:
        text += ANNOTATION_DELIMITER + annotation
    return text


def render_tree(tree: Node, settings: Settings, *, fenced: bool = False) -> str:
    """Render validated rows; complete documents also carry special paths.

    Bare output is for display. Reading it requires its generated special paths.
    """
    return render_tree_with_paths(tree, settings, fenced=fenced)[0]


def render_tree_with_paths(
    tree: Node, settings: Settings, *, fenced: bool = False
) -> tuple[str, dict[int, str]]:
    """Emit rows and their special-path registrations in the same traversal."""
    markdown = settings.style == "list"
    validate_tree(tree)
    rows = [_row(tree, markdown=markdown)]
    registered: dict[int, str] = {}

    def visit(node: Node, prefix: str, depth: int) -> None:
        for index, child in enumerate(node.children):
            if ANNOTATION_DELIMITER in child.name:
                registered[len(rows)] = repo_path(child.path, settings.root)
            last = index == len(node.children) - 1
            if settings.style == "list":
                rows.append("  " * (depth - 1) + "- " + _row(child, markdown=True))
                visit(child, "", depth + 1)
            else:
                tee, end, pipe = ("├── ", "└── ", "│   ")
                if settings.style == "ascii":
                    tee, end, pipe = ("|-- ", "`-- ", "|   ")
                rows.append(prefix + (end if last else tee) + _row(child))
                visit(child, prefix + ("    " if last else pipe), depth + 1)

    visit(tree, "", 1)
    text = "\n".join(rows) + "\n"
    _check_rendered_tree(tree, text, settings, registered)
    if fenced and not markdown:
        # These styles prefix every physical row with './' or a connector, so
        # embedded backticks cannot close the fence. New styles own their framing.
        text = f"```sh\n{text}```\n"
    return text, registered


def _facts(node: Node) -> tuple[object, ...]:
    return (
        node.path,
        node.kind,
        node.target,
        normalize_annotation(node.annotation),
        node.files or None,
        node.dirs or None,
    )


def _check_rendered_tree(
    tree: Node, text: str, settings: Settings, registered: Mapping[int, str]
) -> None:
    try:
        recovered = parse_tree(
            text,
            settings.style,
            root=settings.root,
            special_paths=registered,
        )
    except MarkerError as exc:
        raise MarkerError(
            f"cannot represent tree in {settings.style} style: {exc}"
        ) from exc
    before, after = (tree, *tree.walk()), (recovered, *recovered.walk())
    if tuple(map(_facts, before)) != tuple(map(_facts, after)):
        raise MarkerError(
            f"cannot represent tree in {settings.style} style without changing "
            "a path, kind, target, count, or annotation"
        )


def _counts(rest: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not rest:
        return counts
    match = _COUNT.fullmatch(rest)
    if not match:
        raise MarkerError(f"unrecognized tree suffix: {rest!r}")
    first, unit = int(match[1]), match[2]
    if unit.startswith("folder"):
        if match[3]:
            raise MarkerError("duplicate folder count")
        counts["dirs"] = first
    else:
        counts["files"] = first
        if match[3]:
            counts["dirs"] = int(match[3])
    if any(value == 0 for value in counts.values()):
        raise MarkerError("zero counts are not printed")
    return counts


def _parse_row(
    text: str,
    parent: str,
    *,
    root: bool = False,
    markdown: bool = False,
) -> Node:
    head, _, tail = text.partition(ANNOTATION_DELIMITER)
    annotation = normalize_annotation(tail)
    if root:
        if head not in (".", "./"):  # a hand-written tree may omit the slash
            raise MarkerError("printed tree root must be './'")
        return Node(".", "", KIND_DIR, annotation=annotation)
    return _parse_entry(head, annotation, parent, markdown=markdown)


def _parse_entry(head: str, annotation: str, parent: str, *, markdown: bool) -> Node:
    """Read an entry name and its repository facts after splitting the annotation."""
    kind, name, target, counts = KIND_FILE, head, None, {}
    slash = head.find("/")
    arrow = head.find(f" {SYMLINK_ARROW} ")
    if slash != -1 and (arrow == -1 or slash < arrow):
        kind, name, counts = KIND_DIR, head[:slash], _counts(head[slash + 1 :])
    elif arrow != -1:
        kind, name = KIND_SYMLINK, head[:arrow]
        printed = head[arrow + len(SYMLINK_ARROW) + 2 :]
        target = None if printed == "null" else _read(printed, markdown)
    elif head.endswith(f" {GITLINK_TAG}"):
        kind, name = KIND_GITLINK, head[: -len(GITLINK_TAG) - 1]
    if not name:
        raise MarkerError("missing tree name")
    name = _read(name, markdown)
    return Node(
        name,
        f"{parent}/{name}" if parent else name,
        kind,
        target=target,
        annotation=annotation,
        files=counts.get("files"),
        dirs=counts.get("dirs"),
    )


_INDENTS = {"list": ("  ",), "ascii": ("|   ", "    "), "unicode": ("│   ", "    ")}
_CONNECTORS = {"list": ("- ",), "ascii": ("|-- ", "`-- "), "unicode": ("├── ", "└── ")}


def _depth_row(line: str, style: str) -> tuple[int, str]:
    # No indent unit is also a connector, so stripping indents greedily finds
    # the only possible split, in linear time.
    indents, connectors = _INDENTS[style], _CONNECTORS[style]
    width = len(indents[0])
    offset = 0
    while line.startswith(indents, offset):
        offset += width
    for connector in connectors:
        start = offset + len(connector)
        if line.startswith(connector, offset) and len(line) > start:
            return offset // width + 1, line[start:]
    raise MarkerError(f"invalid {style} tree row: {line!r}")


def detect_style(text: str, *, fenced: bool = False) -> str:
    """Infer connectors; an unfenced root-only document denotes list style."""
    lines = text.splitlines()
    if len(lines) > 1:
        if lines[1].startswith("- "):
            return "list"
        if lines[1].startswith(("|-- ", "`-- ")):
            return "ascii"
        return "unicode"
    return "unicode" if fenced else "list"


def _registered_row(text: str, parent: str, path: str, *, markdown: bool) -> Node:
    """Consume one exact registered name; only its suffix remains to parse."""
    directory, _, name = path.rpartition("/")
    if directory != parent:
        raise MarkerError("special-path parent does not match the row's indentation")
    printed = _display(name, markdown)
    if not text.startswith(printed):
        raise MarkerError("special-path name does not match its registered row")
    suffix = text[len(printed) :]
    if suffix and not suffix.startswith(
        ("/", " [gitlink]", " -> ", ANNOTATION_DELIMITER)
    ):
        raise MarkerError("invalid suffix after registered special-path name")
    node = _parse_row("entry" + suffix, parent, markdown=markdown)
    if node.name != "entry":
        raise MarkerError("invalid suffix after registered special-path name")
    return replace(node, name=name, path=path)


def _registrations(
    paths: Mapping[int, str], root: str, row_count: int
) -> dict[int, str]:
    registered: dict[int, str] = {}
    seen: set[str] = set()
    for row, path in paths.items():
        if type(row) is not int or not 0 < row < row_count:
            raise MarkerError("special-path row must identify an existing non-root row")
        relative = tree_path(path, root)
        if ANNOTATION_DELIMITER not in relative.rsplit("/", 1)[-1]:
            raise MarkerError(
                "special_paths must register a name containing the annotation delimiter"
            )
        if relative in seen:
            raise MarkerError("special_paths contains duplicate paths")
        seen.add(relative)
        registered[row] = relative
    return registered


def _row_parent(stack: list[Node], depth: int) -> Node:
    if depth > len(stack):
        raise MarkerError("tree indentation skips a parent")
    parent = stack[depth - 1]
    if not parent.is_dir:
        raise MarkerError("leaf row cannot have children")
    return parent


def parse_tree(
    text: str,
    style: str | None = None,
    *,
    root: str = ".",
    special_paths: Mapping[int, str] | None = None,
) -> Node:
    """Read structured identities and facts, using registrations before rows."""
    lines = text.splitlines()
    registered = _registrations(special_paths or {}, root, len(lines))
    if not lines:
        raise MarkerError("tree is empty")
    if style is None:
        style = detect_style(text, fenced=True)
    if style not in ("unicode", "ascii", "list"):
        raise MarkerError(f"unknown tree style: {style!r}")
    markdown = style == "list"
    root_node = _parse_row(lines[0], "", root=True, markdown=markdown)
    nodes = {"": root_node}
    children: dict[str, list[str]] = {"": []}
    stack = [root_node]
    for index, line in enumerate(lines[1:], 1):
        depth, row = _depth_row(line, style)
        parent = _row_parent(stack, depth)
        stack = stack[:depth]
        node = (
            _registered_row(row, parent.path, registered[index], markdown=markdown)
            if index in registered
            else _parse_row(row, parent.path, markdown=markdown)
        )
        if node.path in nodes:
            raise MarkerError(f"duplicate tree path: {node.path!r}")
        nodes[node.path] = node
        children.setdefault(parent.path, []).append(node.path)
        stack.append(node)
    for path in reversed(list(nodes)):
        nodes[path] = replace(
            nodes[path],
            children=tuple(nodes[child] for child in children.get(path, [])),
        )
    validate_tree(nodes[""])
    return nodes[""]
