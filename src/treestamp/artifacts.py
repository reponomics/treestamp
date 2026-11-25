"""Container dispatch and publication; editing always consumes one Document.

Markdown preserves its surrounding prose. SVG replaces the drawing from embedded
data. Exporting a copy is a separate operation and never adopts a source target.
"""

from __future__ import annotations

import re
import stat
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, overload

from treestamp.document import (
    Document,
    DocumentSnapshot,
    PreparedWrite,
    _check_expected,
    _read_snapshot,
    parse_document,
    prepare_content,
    prepare_write,
)
from treestamp.errors import MarkerError
from treestamp.gitio import checked_path, document_path
from treestamp.svg import SvgAppearance, parse_svg, render_svg

if TYPE_CHECKING:
    from pathlib import Path

_DEFAULT_APPEARANCE = SvgAppearance()
ArtifactFormat = Literal["markdown", "svg"]
_XML_OPEN = re.compile(rb"<(?:\?xml\b|!DOCTYPE\b|(?:[^\s<>:/]+:)?svg(?:\s|/?>))")
_XML_PROLOG = re.compile(rb"\s*(?:<!--.*?-->|<\?(?!xml\b).*?\?>)", re.DOTALL)


def _looks_like_svg(content: bytes) -> bool:
    """Skip inert XML prolog items without parsing or executing the drawing."""
    content = content.removeprefix(b"\xef\xbb\xbf")
    offset = 0
    while match := _XML_PROLOG.match(content, offset):
        offset = match.end()
    return _XML_OPEN.match(content[offset:].lstrip()) is not None


@dataclass(frozen=True)
class Artifact:
    document: Document
    format: ArtifactFormat = "markdown"
    appearance: SvgAppearance = _DEFAULT_APPEARANCE
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.format not in ("markdown", "svg"):
            raise MarkerError(f"unsupported artifact format: {self.format!r}")


@overload
def parse_artifact(
    content: bytes, *, location: str = "<memory>", allow_absent: Literal[False] = False
) -> Artifact: ...


@overload
def parse_artifact(
    content: bytes, *, location: str = "<memory>", allow_absent: bool
) -> Artifact | None: ...


def parse_artifact(
    content: bytes, *, location: str = "<memory>", allow_absent: bool = False
) -> Artifact | None:
    """Recognized malformed SVG must never become an absent Markdown region."""
    if location.lower().endswith(".svg") or _looks_like_svg(content):
        parsed = parse_svg(content)
        return Artifact(parsed.document, "svg", parsed.appearance, parsed.warnings)
    document = parse_document(content, location=location, allow_absent=allow_absent)
    return Artifact(document) if document is not None else None


def load_artifact(
    path: Path, *, allow_absent: bool = False
) -> tuple[Artifact | None, DocumentSnapshot | None]:
    snapshot = _read_snapshot(path, allow_missing=allow_absent)
    if snapshot is None:
        return None, None
    artifact = parse_artifact(
        snapshot.content, location=str(snapshot.path), allow_absent=allow_absent
    )
    return artifact, snapshot


def prepare_artifact_content(artifact: Artifact, previous: bytes) -> bytes:
    """Same candidate bytes for dirty, check, update, and source writes."""
    if artifact.format == "svg":
        return render_svg(artifact.document, artifact.appearance).encode("utf-8")
    document = artifact.document
    return prepare_content(document, document.settings.root, previous)


def prepare_artifact_write(
    artifact: Artifact,
    destination: Path,
    *,
    expected: DocumentSnapshot | None = None,
    repository: Path | None = None,
) -> PreparedWrite:
    """Prepare a source update; cross-container conversion is an export operation."""
    if artifact.format == "markdown":
        return prepare_write(
            artifact.document, destination, expected=expected, repository=repository
        )
    destination = checked_path(destination)
    previous = _read_snapshot(destination)
    assert previous is not None
    _check_expected(previous, expected)
    existing = parse_artifact(previous.content, location=str(destination))
    if existing.format != "svg":
        raise MarkerError("SVG source writes require a loaded SVG artifact")
    return PreparedWrite(
        destination,
        prepare_artifact_content(artifact, previous.content),
        previous,
        False,
        stat.S_IMODE(destination.stat().st_mode),
        repository,
    )


def is_source_destination(destination: Path, source: Path | None) -> bool:
    """Recognize lexical equality and existing aliases without following symlinks."""
    if source is None:
        return False
    destination, source = checked_path(destination), checked_path(source)
    if destination == source:
        return True
    try:
        return destination.samefile(source)
    except FileNotFoundError:
        return False


def capture_export_destination(
    destination: Path, *, repository: Path, source: Path | None = None
) -> DocumentSnapshot | None:
    """Capture an export target for confirmation without reading it as a tree."""
    destination = checked_path(destination)
    try:
        relative = destination.relative_to(repository)
    except ValueError:
        raise MarkerError("SVG export must stay within the repository") from None
    document_path(repository, relative)
    if destination.suffix.lower() != ".svg":
        raise MarkerError("SVG export requires a .svg destination")
    if is_source_destination(destination, source):
        raise MarkerError("use Write to document to update the loaded source")
    if not destination.parent.is_dir():
        raise MarkerError("SVG export parent directory must already exist")
    return _read_snapshot(destination, allow_missing=True)


def prepare_svg_export(
    document: Document,
    destination: Path,
    *,
    repository: Path,
    appearance: SvgAppearance = _DEFAULT_APPEARANCE,
    source: Path | None = None,
    expected: DocumentSnapshot | None = None,
) -> PreparedWrite:
    """Prepare a separate copy, requiring captured confirmation for replacement."""
    destination = checked_path(destination)
    previous = capture_export_destination(
        destination, repository=repository, source=source
    )
    if expected is None and previous is not None:
        raise MarkerError("file already exists; confirm replacement before exporting")
    if expected is not None and previous != expected:
        raise MarkerError("export destination changed; review it before replacing")
    content = render_svg(document, appearance).encode("utf-8")
    mode = stat.S_IMODE(destination.stat().st_mode) if previous is not None else None
    return PreparedWrite(
        destination, content, previous, previous is None, mode, repository
    )
