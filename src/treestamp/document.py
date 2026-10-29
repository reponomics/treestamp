"""Printed-tree documents and atomic publication, independent of any editor."""

from __future__ import annotations

import json
import os
import re
import stat
import tempfile
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, overload

from treestamp.codec import detect_style, parse_tree, render_tree_with_paths
from treestamp.errors import MarkerError
from treestamp.gitio import checked_path, document_path
from treestamp.model import Node, Settings, read_path_value, tree_path


@dataclass(frozen=True)
class Document:
    tree: Node
    settings: Settings = Settings()
    hidden: frozenset[str] = frozenset()


class _FenceTracker:
    def __init__(self) -> None:
        self.char = ""
        self.length = 0

    def update(self, line: str) -> bool:
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if self.char:
            if (
                match
                and match[1][0] == self.char
                and len(match[1]) >= self.length
                and not match[2].strip()
            ):
                self.char = ""
            return True
        if match:
            self.char, self.length = match[1][0], len(match[1])
            return True
        return False


START_MARKER = "<!-- treestamp:start -->"
END_MARKER = "<!-- treestamp:end -->"
CONFIG_START = "<!-- treestamp:config"
DEFAULT_DOCUMENT_FILE = "README.md"
_BOUNDARY = re.compile(r"^[ \t]*<!--[ \t]*treestamp:(?:start|end)")


@dataclass(frozen=True)
class DocumentSnapshot:
    path: Path
    content: bytes


@dataclass(frozen=True)
class PreparedWrite:
    path: Path
    content: bytes
    previous: DocumentSnapshot | None
    create: bool
    mode: int | None
    repository: Path | None = None


@dataclass
class _Region:
    start: int | None = None
    end: int | None = None
    eol: bytes = b"\n"

    def accept(self, kind: str, offset: int, line: bytes, location: str) -> None:
        if kind == START_MARKER:
            if self.start is not None:
                raise MarkerError(
                    "expected exactly one pair; duplicate or nested start marker",
                    location=location,
                )
            self.start = offset + len(line)
            self.eol = b"\r\n" if line.endswith(b"\r\n") else b"\n"
        else:
            if self.start is None or self.end is not None:
                raise MarkerError(
                    "unmatched or misordered end marker", location=location
                )
            self.end = offset


def _line_body(line: bytes, offset: int) -> str:
    body = line.rstrip(b"\r\n").decode("utf-8", "surrogateescape")
    return body.removeprefix("\ufeff") if offset == 0 else body


def _marker_kind(body: str, location: str) -> str | None:
    if not _BOUNDARY.match(body):
        return None
    if body.startswith((" ", "\t")):
        raise MarkerError(
            "treestamp boundary markers must not be indented", location=location
        )
    kind = body.rstrip()
    if kind not in (START_MARKER, END_MARKER):
        raise MarkerError("malformed treestamp boundary marker", location=location)
    return kind


def _find_region(content: bytes, location: str) -> _Region | None:
    """Ignore fenced examples outside the pair; its old interior stays opaque."""
    region, fences = _Region(), _FenceTracker()
    offset = 0
    for line in content.splitlines(keepends=True):
        body = _line_body(line, offset)
        interior = region.start is not None and region.end is None
        if interior or not fences.update(body):
            kind = _marker_kind(body, location)
            if kind is not None:
                region.accept(kind, offset, line, location)
        offset += len(line)
    if region.start is None:
        return None
    if region.end is None:
        raise MarkerError(
            "unmatched start marker; missing end marker", location=location
        )
    return region


def extract_region(content: bytes, *, location: str = "<memory>") -> bytes:
    """Return the exact managed region, including boundary lines and their endings."""
    region = _find_region(content, location)
    if region is None:
        raise MarkerError("document has no treestamp marker pair", location=location)
    assert region.start is not None and region.end is not None
    start = content.rfind(b"\n", 0, region.start - 1) + 1
    end = content.find(b"\n", region.end)
    return content[start:] if end == -1 else content[start : end + 1]


def _read_snapshot(
    path: Path, *, allow_missing: bool = False
) -> DocumentSnapshot | None:
    path = checked_path(path)
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        if allow_missing:
            return None
        raise MarkerError("document does not exist", location=str(path)) from None
    if not stat.S_ISREG(mode):
        raise MarkerError("document must be a regular file", location=str(path))
    return DocumentSnapshot(path, path.read_bytes())


def _path_array(value: object, key: str, root: str) -> frozenset[str]:
    if not isinstance(value, list):
        raise MarkerError(f"{key} must be an array of exact paths")
    paths = [read_path_value(item) for item in value]
    for path in paths:
        tree_path(path, root)
    if len(set(paths)) != len(paths):
        raise MarkerError(f"{key} contains duplicate paths")
    return frozenset(paths)


def _special_path_record(item: object) -> tuple[int, object]:
    if isinstance(item, str) or isinstance(item, dict) and set(item) == {"git_bytes"}:
        raise MarkerError("legacy special_paths format; regenerate this treestamp")
    if not isinstance(item, dict) or set(item) != {"row", "path"}:
        raise MarkerError("each special_paths record must contain row and path")
    row = item["row"]
    if type(row) is not int or row <= 0:
        raise MarkerError("special-path row must be a positive integer")
    return row, item["path"]


def _special_path_array(value: object) -> dict[int, str]:
    if not isinstance(value, list):
        raise MarkerError("special_paths must be an array of row/path records")
    result: dict[int, str] = {}
    for item in value:
        row, path = _special_path_record(item)
        if row in result:
            raise MarkerError("special_paths contains duplicate rows")
        result[row] = read_path_value(path)
    return result


def _metadata(text: str) -> tuple[Settings, frozenset[str], dict[int, str]]:
    try:
        values = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise MarkerError(f"invalid document metadata: {exc}") from exc
    unknown = values.keys() - {"root", "hidden", "special_paths"}
    if unknown:
        raise MarkerError(f"unknown document settings: {', '.join(sorted(unknown))}")
    settings = Settings(root=read_path_value(values.get("root", ".")))
    hidden = _path_array(values.get("hidden", []), "hidden", settings.root)
    special = _special_path_array(values.get("special_paths", []))
    return settings, hidden, special


def _trim_blank_lines(text: str) -> str:
    lines = text.split("\n")
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).lstrip()


def _split_metadata(text: str) -> tuple[str, str]:
    first, separator, rest = text.partition("\n")
    if first.strip() != CONFIG_START or not separator:
        raise MarkerError("malformed metadata wrapper")
    payload, separator, tree = rest.partition("\n-->")
    if not separator or "<!--" in payload or "-->" in payload:
        raise MarkerError("invalid or unterminated metadata wrapper")
    return payload, _trim_blank_lines(tree)


def _unfence(text: str) -> str:
    if not text.startswith(("```", "~~~")):
        return text
    lines = text.splitlines()
    match = re.fullmatch(r"(`{3,}|~{3,})(?:[A-Za-z]+)?", lines[0])
    if not match:
        return text
    if len(lines) < 3 or lines[-1].rstrip() != match[1]:
        raise MarkerError("invalid tree code fence")
    return "\n".join(lines[1:-1])


def _parse_interior(interior: bytes) -> Document:
    text = _trim_blank_lines(
        interior.decode("utf-8", "surrogateescape").replace("\r\n", "\n")
    )
    settings = Settings()
    hidden: frozenset[str] = frozenset()
    special: dict[int, str] = {}
    if text.startswith(CONFIG_START):
        payload, text = _split_metadata(text)
        settings, hidden, special = _metadata(payload)
    body = _unfence(text)
    style = detect_style(body, fenced=body != text)
    tree = parse_tree(body, style, root=settings.root, special_paths=special)
    collapsed = [node for node in tree.walk() if node.is_dir and not node.children]
    visibility = {bool(node.files or node.dirs) for node in collapsed}
    if len(visibility) > 1:
        raise MarkerError("collapsed directories must use consistent count visibility")
    settings = replace(settings, style=style, show_counts=next(iter(visibility), True))
    document = Document(tree, settings, hidden)
    if normalized_hidden(document) != hidden:
        raise MarkerError("hidden paths require a printed expanded parent")
    return document


@overload
def parse_document(
    content: bytes, *, location: str = "<memory>", allow_absent: Literal[False] = False
) -> Document: ...


@overload
def parse_document(
    content: bytes, *, location: str = "<memory>", allow_absent: bool
) -> Document | None: ...


def parse_document(
    content: bytes, *, location: str = "<memory>", allow_absent: bool = False
) -> Document | None:
    """Read once; optional loads allow absent regions, never empty or malformed ones."""
    region = _find_region(content, location)
    if region is None:
        if allow_absent:
            return None
        raise MarkerError("document has no treestamp marker pair", location=location)
    interior = content[region.start : region.end]
    return _parse_interior(interior)


def load_document(
    path: Path, *, allow_absent: bool = False
) -> tuple[Document | None, DocumentSnapshot | None]:
    snapshot = _read_snapshot(path, allow_missing=allow_absent)
    if snapshot is None:
        return None, None
    document = parse_document(
        snapshot.content, location=str(snapshot.path), allow_absent=allow_absent
    )
    return document, snapshot


def _quote(value: str) -> str:
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("\x7f", "\\u007f")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _path_literal(value: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        encoded = value.encode("utf-8", "surrogateescape").hex()
        return f'{{git_bytes = "{encoded}"}}'
    return _quote(value)


def normalized_hidden(document: Document) -> frozenset[str]:
    """Project explicit repository-relative hiding onto printed expanded parents."""
    nodes = {node.path: node for node in [document.tree, *document.tree.walk()]}
    expanded = {
        path
        for path, node in nodes.items()
        if node.is_dir and (node.children or not path)
    }
    result = set()
    for path in document.hidden:
        relative = tree_path(path, document.settings.root)
        if relative in nodes:
            raise MarkerError(f"path is both printed and hidden: {path!r}")
        if relative.rpartition("/")[0] in expanded:
            result.add(path)
    return frozenset(result)


def _settings_text(document: Document, registered: dict[int, str]) -> str:
    rows = []
    if document.settings.root != ".":
        rows.append(f"root = {_path_literal(document.settings.root)}")
    hidden = normalized_hidden(document)
    if hidden:
        values = ", ".join(_path_literal(path) for path in sorted(hidden))
        rows.append(f"hidden = [{values}]")
    if registered:
        values = ", ".join(
            f"{{row = {row}, path = {_path_literal(path)}}}"
            for row, path in registered.items()
        )
        rows.append(f"special_paths = [{values}]")
    return "".join(row + "\n" for row in rows)


def render_interior(document: Document, root: str | None = None) -> str:
    """Render the interior using repository-relative config identities."""
    if root is not None:
        document = replace(document, settings=replace(document.settings, root=root))
    body, registered = render_tree_with_paths(
        document.tree, document.settings, fenced=True
    )
    payload = _settings_text(document, registered)
    output = f"{CONFIG_START}\n{payload}-->\n{body}" if payload else body
    # Validate framing and metadata together before any bytes can be published.
    _parse_interior(output.encode("utf-8", "surrogateescape"))
    return output


def same_content(left: Document, right: Document, root: str) -> bool:
    """Compare both documents in the current format, ignoring serialization noise."""
    return render_interior(left, root) == render_interior(right, root)


def render_region(document: Document, root: str | None = None) -> str:
    """Render the complete treestamp, markers included."""
    return f"{START_MARKER}\n{render_interior(document, root)}{END_MARKER}\n"


def validate_source_tree(tree: Node, settings: Settings) -> None:
    """Preflight every selected source entry, irrespective of display curation."""
    try:
        render_region(Document(tree, settings))
    except MarkerError as exc:
        raise MarkerError(
            "this selected tree contains entries that this release cannot load "
            f"safely: {exc}"
        ) from exc


def prepare_content(
    document: Document, root: str, previous: bytes, *, location: str = "<memory>"
) -> bytes:
    """Splice the rendered region into existing bytes, as a write would.

    The region keeps the document's line-ending convention; bytes outside the
    marker pair are untouched. This is the check and update comparison.
    """
    region = _find_region(previous, location)
    if region is None:
        raise MarkerError("document has no treestamp marker pair", location=location)
    interior = render_interior(document, root).encode("utf-8", "surrogateescape")
    interior = interior.replace(b"\n", region.eol)
    return previous[: region.start] + interior + previous[region.end :]


def _check_expected(
    previous: DocumentSnapshot, expected: DocumentSnapshot | None
) -> None:
    if expected is None or checked_path(expected.path) != previous.path:
        return
    if expected.content != previous.content:
        raise MarkerError(
            "document changed since it was loaded or written; "
            "load again before writing",
            location=str(previous.path),
        )


def prepare_write(
    document: Document,
    destination: Path,
    *,
    create: bool = False,
    expected: DocumentSnapshot | None = None,
    repository: Path | None = None,
) -> PreparedWrite:
    """Prepare complete bytes without loading any discarded destination config."""
    destination = checked_path(destination)
    if create:
        if destination.exists():
            raise MarkerError(
                "file already exists; Create requires a new path",
                location=str(destination),
            )
        content = render_region(document).encode("utf-8", "surrogateescape")
        return PreparedWrite(destination, content, None, True, None, repository)
    previous = _read_snapshot(destination)
    assert previous is not None
    _check_expected(previous, expected)
    content = prepare_content(
        document,
        document.settings.root,
        previous.content,
        location=str(destination),
    )
    mode = stat.S_IMODE(destination.stat().st_mode)
    return PreparedWrite(destination, content, previous, False, mode, repository)


def _check_current(prepared: PreparedWrite) -> None:
    if prepared.repository is not None:
        document_path(
            prepared.repository, prepared.path.relative_to(prepared.repository)
        )
    current = _read_snapshot(prepared.path, allow_missing=True)
    if prepared.create:
        if current is not None:
            raise MarkerError(
                "file already exists; Create requires a new path",
                location=str(prepared.path),
            )
    elif current != prepared.previous:
        raise MarkerError(
            "document changed after write preparation", location=str(prepared.path)
        )


def publish_write(prepared: PreparedWrite) -> DocumentSnapshot:
    """Publish atomically after a best-effort conflict check, not a global FS lock."""
    _check_current(prepared)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".treestamp-", dir=prepared.path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(prepared.content)
        if prepared.mode is not None:
            os.chmod(temporary, prepared.mode)
        _check_current(prepared)
        if prepared.create:
            os.link(temporary, prepared.path)
        else:
            os.replace(temporary, prepared.path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return DocumentSnapshot(prepared.path, prepared.content)


def write_document(
    document: Document,
    destination: Path,
    *,
    create: bool = False,
    expected: DocumentSnapshot | None = None,
    repository: Path | None = None,
) -> DocumentSnapshot:
    return publish_write(
        prepare_write(
            document,
            destination,
            create=create,
            expected=expected,
            repository=repository,
        )
    )
