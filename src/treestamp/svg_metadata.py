"""Versioned SVG envelope; the existing text codec remains the data authority.

This is a bounded metadata reader, not an SVG sanitizer. Imported drawing markup
must never be executed or inserted into a page: callers regenerate it instead.
The parser receives one complete, capped buffer and rejects DTDs at their start,
before any declarations or entities can be processed. No resource is resolved.
"""

from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass, replace
from xml.parsers import expat
from xml.sax.saxutils import quoteattr

from treestamp.document import Document, extract_region, parse_document, render_region
from treestamp.errors import MarkerError
from treestamp.model import MAX_DEPTH, Settings

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
PAYLOAD_NAMESPACE = "urn:treestamp:svg:1"
MAX_SVG_BYTES = 1024 * 1024
MAX_PAYLOAD_BYTES = 256 * 1024
MAX_ROWS = 10_000
MAX_XML_DEPTH = 64
MAX_XML_ELEMENTS = 50_000
MAX_NAMESPACE_CHARS = 256
_MAX_BASE64_CHARS = 4 * ((MAX_PAYLOAD_BYTES + 2) // 3)
_SVG = f"{SVG_NAMESPACE} svg"
_METADATA = f"{SVG_NAMESPACE} metadata"
_PAYLOAD = f"{PAYLOAD_NAMESPACE} treestamp"
_ATTRIBUTES = frozenset(
    ("version", "codec", "encoding", "text_style", "show_counts", "style", "theme")
)


@dataclass(frozen=True)
class SvgAppearance:
    """Artifact preferences, independent of text notation and editor state.

    Syntactically valid unknown style identifiers can be read for fallback;
    the artifact writer separately requires a registered visual style.
    """

    style: str = "continuous"
    theme: str = "light"

    def __post_init__(self) -> None:
        if not isinstance(self.style, str) or not re.fullmatch(
            r"[a-z][a-z0-9-]{0,63}", self.style
        ):
            raise MarkerError("SVG style must be a short lowercase identifier")
        if self.theme not in ("light", "dark"):
            raise MarkerError("SVG theme must be light or dark")


@dataclass(frozen=True)
class SvgArtifact:
    document: Document
    appearance: SvgAppearance = SvgAppearance()
    warnings: tuple[str, ...] = ()


def validate_document_bounds(document: Document) -> None:
    """Bound work before rendering, including callers supplying an in-memory tree."""
    stack = [(document.tree, 0)]
    count = 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_ROWS:
            raise MarkerError(f"SVG exceeds the {MAX_ROWS:,}-row limit")
        if depth > MAX_DEPTH:
            raise MarkerError(f"SVG tree exceeds the {MAX_DEPTH}-level depth limit")
        stack.extend((child, depth + 1) for child in node.children)


def _preferences(document: Document, attrs: dict[str, str]) -> Document:
    flag = attrs["show_counts"]
    if flag not in ("true", "false"):
        raise MarkerError("SVG show_counts must be true or false")
    return apply_text_preferences(document, attrs["text_style"], flag == "true")


def apply_text_preferences(
    document: Document, text_style: str, show_counts: bool
) -> Document:
    """Restore explicit text preferences after parsing a serialized region.

    Hosted export and SVG metadata use the same contradiction checks. The
    existing codec remains authoritative for every observable document fact.
    """
    settings = Settings(
        root=document.settings.root,
        style=text_style,
        show_counts=show_counts,
        attribution=document.settings.attribution,
    )
    preferred = replace(document, settings=settings)
    if render_region(preferred) != render_region(document):
        raise MarkerError("SVG text_style contradicts the embedded textual treestamp")
    if not settings.show_counts and any(
        node.files or node.dirs for node in [document.tree, *document.tree.walk()]
    ):
        raise MarkerError("SVG show_counts contradicts positive embedded counts")
    return preferred


def encode_metadata(document: Document, appearance: SvgAppearance) -> str:
    """Render only the standard metadata element, usable by every visual style."""
    validate_document_bounds(document)
    payload = render_region(document).encode("utf-8", "surrogateescape")
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise MarkerError("SVG textual payload exceeds the 256 KiB limit")
    attrs = {
        "version": "1",
        "codec": "treestamp-text-v1",
        "encoding": "base64",
        "text_style": document.settings.style,
        "show_counts": str(document.settings.show_counts).lower(),
        "style": appearance.style,
        "theme": appearance.theme,
    }
    # Writers enforce the same preference consistency as readers.
    _preferences(parse_document(payload), attrs)
    attributes = " ".join(f"{key}={quoteattr(value)}" for key, value in attrs.items())
    encoded = base64.b64encode(payload).decode("ascii")
    return (
        f'<metadata><ts:treestamp xmlns:ts="{PAYLOAD_NAMESPACE}" {attributes}>'
        f"{encoded}</ts:treestamp></metadata>"
    )


class _MetadataReader:
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.elements = 0
        self.attrs: dict[str, str] | None = None
        self.parts: list[str] = []
        self.size = 0
        self.in_payload = False

    def start(self, name: str, attrs: dict[str, str]) -> None:
        self.elements += 1
        if self.elements > MAX_XML_ELEMENTS or len(self.stack) >= MAX_XML_DEPTH:
            raise MarkerError("SVG XML exceeds the element or nesting limit")
        if not self.stack and name != _SVG:
            raise MarkerError("expected an SVG root in the SVG namespace")
        if self.in_payload:
            raise MarkerError("SVG treestamp payload must contain only base64 text")
        if name == _PAYLOAD:
            self._payload(attrs)
        self.stack.append(name)

    def _payload(self, attrs: dict[str, str]) -> None:
        if self.attrs is not None:
            raise MarkerError("SVG contains duplicate treestamp payloads")
        if self.stack != [_SVG, _METADATA]:
            raise MarkerError("SVG treestamp payload must be a direct metadata child")
        if set(attrs) != _ATTRIBUTES:
            raise MarkerError("SVG treestamp metadata has missing or unknown fields")
        for key, expected in (
            ("version", "1"),
            ("codec", "treestamp-text-v1"),
            ("encoding", "base64"),
        ):
            if attrs[key] != expected:
                raise MarkerError(f"unsupported SVG treestamp {key}: {attrs[key]!r}")
        self.attrs = attrs
        self.in_payload = True

    def end(self, name: str) -> None:
        if name == _PAYLOAD:
            self.in_payload = False
        self.stack.pop()

    def text(self, data: str) -> None:
        if self.in_payload:
            self.size += len(data)
            if self.size > _MAX_BASE64_CHARS:
                raise MarkerError("SVG textual payload exceeds the 256 KiB limit")
            self.parts.append(data)

    def artifact(self) -> SvgArtifact:
        if self.attrs is None:
            raise MarkerError("SVG has no editable treestamp metadata payload")
        try:
            payload = base64.b64decode("".join(self.parts), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise MarkerError("SVG treestamp payload is not valid base64") from exc
        if len(payload) > MAX_PAYLOAD_BYTES:
            raise MarkerError("SVG textual payload exceeds the 256 KiB limit")
        document = parse_document(payload)
        if extract_region(payload) != payload:
            raise MarkerError(
                "SVG payload must contain only a complete treestamp region"
            )
        validate_document_bounds(document)
        document = _preferences(document, self.attrs)
        return SvgArtifact(
            document,
            SvgAppearance(style=self.attrs["style"], theme=self.attrs["theme"]),
        )


def _reject_declaration(*_args: object) -> None:
    raise MarkerError("SVG DTDs and entity declarations are not supported")


def _reject_external(*_args: object) -> int:
    raise MarkerError("SVG external entities are not supported")


def _namespace(_prefix: str | None, uri: str | None) -> None:
    # Namespace expansion can otherwise multiply a long URI into every element
    # and attribute name, despite a small source buffer and bounded nesting.
    if uri is not None and len(uri) > MAX_NAMESPACE_CHARS:
        raise MarkerError("SVG namespace exceeds the 256-character limit")


def read_metadata(content: bytes) -> SvgArtifact:
    """Read a capped whole buffer without interpreting or resolving its drawing."""
    if len(content) > MAX_SVG_BYTES:
        raise MarkerError("SVG exceeds the 1 MiB file limit")
    reader = _MetadataReader()
    parser = expat.ParserCreate(namespace_separator=" ")
    parser.StartElementHandler = reader.start
    parser.EndElementHandler = reader.end
    parser.CharacterDataHandler = reader.text
    parser.StartNamespaceDeclHandler = _namespace
    parser.StartDoctypeDeclHandler = _reject_declaration
    parser.EntityDeclHandler = _reject_declaration
    parser.ExternalEntityRefHandler = _reject_external
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(content, True)
    except expat.ExpatError as exc:
        raise MarkerError(f"invalid SVG XML: {exc}") from exc
    return reader.artifact()
