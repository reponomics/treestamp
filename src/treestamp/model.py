"""Immutable tree data and initial layout; no Git or UI dependencies."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from treestamp.errors import MarkerError

if TYPE_CHECKING:
    from collections.abc import Iterable

KIND_FILE = "file"
KIND_DIR = "dir"
KIND_SYMLINK = "symlink"
KIND_GITLINK = "gitlink"
KINDS = frozenset((KIND_FILE, KIND_DIR, KIND_SYMLINK, KIND_GITLINK))
MAX_DEPTH = 128
ANNOTATION_DELIMITER = "  # "


@dataclass(frozen=True)
class Entry:
    path: str
    kind: str = KIND_FILE
    target: str | None = None


@dataclass(frozen=True)
class Node:
    name: str
    path: str
    kind: str
    children: tuple[Node, ...] = ()
    target: str | None = None
    annotation: str = ""
    files: int | None = None
    dirs: int | None = None

    @property
    def is_dir(self) -> bool:
        return self.kind == KIND_DIR

    def walk(self) -> list[Node]:
        """Return descendants in printed order, excluding this node."""
        out: list[Node] = []
        stack = list(reversed(self.children))
        while stack:
            node = stack.pop()
            out.append(node)
            stack.extend(reversed(node.children))
        return out


@dataclass(frozen=True)
class Settings:
    """Editor presentation and selected scope, not the document config schema."""

    root: str = "."
    style: str = "unicode"
    show_counts: bool = True

    def __post_init__(self) -> None:
        if self.root != ".":
            validate_path(self.root)
        if self.style not in ("unicode", "ascii", "list"):
            raise MarkerError("style must be unicode, ascii, or list")
        if type(self.show_counts) is not bool:
            raise MarkerError("show_counts must be a boolean")


def repo_path(path: str, root: str) -> str:
    """Convert a tree-relative identity to its repository-relative identity."""
    if root != ".":
        validate_path(root)
    if path:
        validate_path(path)
    if not path:
        return root
    return path if root == "." else f"{root}/{path}"


def tree_path(path: str, root: str) -> str:
    """Validate a repository-relative child identity and scope it to root."""
    validate_path(path)
    if root == ".":
        return path
    validate_path(root)
    prefix = root + "/"
    if not path.startswith(prefix):
        raise MarkerError(f"path is outside selected root or names root: {path!r}")
    return path[len(prefix) :]


def path_value(path: str) -> str | dict[str, str]:
    """Encode a Git identity losslessly in config or JSON."""
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        return {"git_bytes": path.encode("utf-8", "surrogateescape").hex()}
    return path


def read_path_value(value: object) -> str:
    """Decode the public string/byte path representation without normalizing it."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and set(value) == {"git_bytes"}:
        encoded = value["git_bytes"]
        if isinstance(encoded, str):
            try:
                return bytes.fromhex(encoded).decode("utf-8", "surrogateescape")
            except ValueError:
                pass
    raise MarkerError('path must be a string or {git_bytes = "hexadecimal bytes"}')


def validate_path(path: str) -> None:
    if (
        not isinstance(path, str)
        or "\x00" in path
        or any(component in ("", ".", "..") for component in path.split("/"))
    ):
        raise MarkerError(f"invalid relative path: {path!r}")
    if path.count("/") >= MAX_DEPTH:
        raise MarkerError(f"path exceeds the {MAX_DEPTH}-level depth limit")
    try:
        path.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError as exc:
        raise MarkerError(f"invalid path encoding: {path!r}") from exc


def validate_paths(paths: Iterable[str]) -> None:
    leaves: set[str] = set()
    for path in paths:
        validate_path(path)
        if path in leaves:
            raise MarkerError(f"duplicate source path: {path!r}")
        leaves.add(path)
    for path in leaves:
        parts = path.split("/")
        if any("/".join(parts[:i]) in leaves for i in range(1, len(parts))):
            raise MarkerError(f"source leaf has descendants: {path!r}")


def sort_nodes(nodes: Iterable[Node]) -> tuple[Node, ...]:
    return tuple(
        sorted(
            nodes,
            key=lambda n: (not n.is_dir, n.name.encode("utf-8", "surrogateescape")),
        )
    )


def validate_tree(root: Node, *, full: bool = False) -> None:
    """Validate structure; full targets cannot contain empty directories."""
    if root.path or not root.is_dir or root.name != ".":
        raise MarkerError("tree root must be a directory named '.' with path ''")
    seen: set[str] = set()
    for node in [root, *root.walk()]:
        _validate_node(node)
        _validate_tree_position(node, full=full)
        if node.path in seen:
            raise MarkerError(f"duplicate tree path: {node.path!r}")
        seen.add(node.path)


def _validate_tree_position(node: Node, *, full: bool) -> None:
    if node.path:
        validate_path(node.path)
        if node.name != node.path.rsplit("/", 1)[-1]:
            raise MarkerError(f"name does not match path: {node.path!r}")
        if full and node.is_dir and not node.children:
            raise MarkerError(
                f"target directory has no tracked descendants: {node.path}"
            )
    for child in node.children:
        expected = f"{node.path}/{child.name}" if node.path else child.name
        if child.path != expected:
            raise MarkerError(f"invalid child path: {child.path!r}")


def _validate_counts(node: Node) -> None:
    for value in (node.files, node.dirs):
        if value is not None and (type(value) is not int or value < 0):
            raise MarkerError("counts must be nonnegative integers")
    if node.files is None and node.dirs is None:
        return
    if not node.is_dir or node.children or not node.path:
        raise MarkerError("counts belong only to collapsed non-root directories")


def normalize_annotation(text: str) -> str:
    """Keep annotations literal and on one line; tabs occupy two spaces."""
    if not isinstance(text, str):
        raise MarkerError("annotation must be text")
    if any(not character.isprintable() and character != "\t" for character in text):
        raise MarkerError("annotation must be a single line of printable text or tabs")
    return text.replace("\t", "  ")


def _validate_node(node: Node) -> None:
    if node.kind not in KINDS:
        raise MarkerError(f"unknown kind: {node.kind!r}")
    if node.children and not node.is_dir:
        raise MarkerError(f"leaf has children: {node.path!r}")
    if node.target is not None:
        if node.kind != KIND_SYMLINK:
            raise MarkerError("only symlinks have targets")
        if not isinstance(node.target, str):
            raise MarkerError("symlink target must be text or null")
    normalize_annotation(node.annotation)
    _validate_counts(node)


def build_tree(entries: Iterable[Entry], root_name: str = ".") -> Node:
    """Build a complete tree from tracked leaves, with deterministic ordering."""
    rows = list(entries)
    validate_paths(entry.path for entry in rows)
    nodes: dict[str, Node] = {"": Node(root_name, "", KIND_DIR)}
    children: dict[str, list[str]] = {"": []}
    for entry in rows:
        if entry.kind not in KINDS - {KIND_DIR}:
            raise MarkerError(f"source entry must be a tracked leaf: {entry.path!r}")
        parts = entry.path.split("/")
        for i, name in enumerate(parts):
            path = "/".join(parts[: i + 1])
            parent = "/".join(parts[:i])
            if path not in nodes:
                nodes[path] = Node(name, path, KIND_DIR)
                children.setdefault(parent, []).append(path)
            if i == len(parts) - 1:
                nodes[path] = Node(name, path, entry.kind, target=entry.target)
    for path in sorted(nodes, key=lambda p: p.count("/") + bool(p), reverse=True):
        node = nodes[path]
        if node.is_dir:
            nodes[path] = replace(
                node,
                children=sort_nodes(nodes[child] for child in children.get(path, [])),
            )
    validate_tree(nodes[""], full=True)
    return nodes[""]


def with_counts(node: Node, target: Node, settings: Settings) -> Node:
    """Refresh immediate, unfiltered counts on a collapsed directory."""
    if not node.path or not node.is_dir or node.children or not settings.show_counts:
        return replace(node, files=None, dirs=None)
    files = sum(not child.is_dir for child in target.children)
    dirs = sum(child.is_dir for child in target.children)
    # A zero count is not printed, so it is not carried either.
    return replace(
        node,
        files=files or None,
        dirs=dirs or None,
    )


def initial_tree(target: Node, settings: Settings) -> Node:
    """Show exactly the root's immediate children, with directories collapsed."""
    validate_tree(target, full=True)
    children = tuple(
        with_counts(replace(child, children=()), child, settings)
        for child in target.children
    )
    return replace(target, children=children)
