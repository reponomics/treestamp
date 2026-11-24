"""Untrusted XML and versioned envelope contract, including independent fixtures."""

import base64
from unittest.mock import Mock

import pytest

from treestamp.document import Document
from treestamp.errors import MarkerError
from treestamp.model import Node
from treestamp.svg import parse_svg, render_svg, render_svg_metadata
from treestamp.svg_metadata import (
    MAX_PAYLOAD_BYTES,
    MAX_SVG_BYTES,
    MAX_XML_DEPTH,
    MAX_XML_ELEMENTS,
    _reject_external,
)

REGION = b"<!-- treestamp:start -->\n```text\n./\n```\n<!-- treestamp:end -->\n"


def envelope(payload: bytes = REGION, attrs: str = "", *, encode: bool = True) -> bytes:
    encoded = base64.b64encode(payload) if encode else payload
    fields = attrs or (
        'version="1" codec="treestamp-text-v1" encoding="base64" '
        'text_style="unicode" show_counts="true" style="continuous" theme="light"'
    )
    return (
        (
            '<svg xmlns="http://www.w3.org/2000/svg"><metadata>'
            '<t:treestamp xmlns:t="urn:treestamp:svg:1" '
            f"{fields}>"
        ).encode()
        + encoded
        + b"</t:treestamp></metadata></svg>"
    )


def test_independent_fixture() -> None:
    assert parse_svg(envelope()).document == Document(Node(".", "", "dir"))


@pytest.mark.parametrize(
    "field,old,new",
    [
        ("version", "1", "2"),
        ("codec", "treestamp-text-v1", "future-codec"),
        ("encoding", "base64", "gzip"),
        ("theme", "light", "system"),
        ("text_style", "unicode", "list"),
        ("show_counts", "true", "1"),
        ("style", "continuous", "../../bad"),
    ],
)
def test_invalid_or_unsupported_fields(field: str, old: str, new: str) -> None:
    data = envelope().replace(f'{field}="{old}"'.encode(), f'{field}="{new}"'.encode())
    with pytest.raises(MarkerError):
        parse_svg(data)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda svg: svg.replace(b' theme="light"', b""),
        lambda svg: svg.replace(b' theme="light"', b' theme="light" extra="value"'),
        lambda svg: svg.replace(b'xmlns="http://www.w3.org/2000/svg"', b""),
        lambda svg: svg.replace(b"urn:treestamp:svg:1", b"urn:treestamp:svg:2"),
        lambda svg: svg.replace(b"</t:treestamp>", b"<g/></t:treestamp>"),
        lambda svg: svg.replace(b"<metadata>", b"<g><metadata>").replace(
            b"</metadata>", b"</metadata></g>"
        ),
        lambda svg: svg.replace(b"<metadata>", b"").replace(b"</metadata>", b""),
        lambda svg: svg[:-5],
    ],
)
def test_missing_wrong_location_or_malformed_envelope(mutation: object) -> None:
    with pytest.raises(MarkerError):
        parse_svg(mutation(envelope()))  # type: ignore[operator]


def test_duplicate_payload_rejected() -> None:
    svg = envelope()
    metadata = svg[
        svg.index(b"<metadata>") : svg.index(b"</metadata>") + len(b"</metadata>")
    ]
    with pytest.raises(MarkerError, match="duplicate"):
        parse_svg(svg.replace(b"</svg>", metadata + b"</svg>"))


@pytest.mark.parametrize(
    "payload", [b"!", b"AAAA=", b"ww==\n", b"\xc3\xa9", b"", b"Cg=="]
)
def test_invalid_base64_or_invalid_text_document(payload: bytes) -> None:
    with pytest.raises(MarkerError):
        parse_svg(envelope(payload, encode=False))


def test_payload_is_exact_complete_region_without_readme_prose() -> None:
    with pytest.raises(MarkerError, match="only a complete"):
        parse_svg(envelope(b"Prose before\n" + REGION))


@pytest.mark.parametrize(
    "declaration",
    [
        b'<!DOCTYPE svg SYSTEM "https://example.invalid/remote.dtd">',
        b'<!DOCTYPE svg [<!ENTITY x "expanded">]>',
        b'<!DOCTYPE svg [<!ENTITY % ext SYSTEM "file:///etc/passwd">%ext;]>',
        b'<!DOCTYPE svg [<!ENTITY x "&x;&x;&x;">]>',
    ],
)
def test_dtd_rejected_before_entity_or_body_processing(
    declaration: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    from treestamp import svg_metadata

    start = Mock(side_effect=AssertionError("body must not be processed"))
    monkeypatch.setattr(svg_metadata._MetadataReader, "start", start)
    with pytest.raises(MarkerError, match="DTDs"):
        parse_svg(declaration + envelope())
    start.assert_not_called()


def test_external_resolution_handler_cannot_resolve() -> None:
    with pytest.raises(MarkerError, match="external entities"):
        _reject_external(None, None, "https://example.invalid/", None)


def test_full_file_limit_precedes_xml_parsing() -> None:
    with pytest.raises(MarkerError, match="1 MiB"):
        parse_svg(b"!" * (MAX_SVG_BYTES + 1))


def test_encoded_payload_limit() -> None:
    with pytest.raises(MarkerError, match="256 KiB"):
        parse_svg(envelope(b"x" * (MAX_PAYLOAD_BYTES + 4)))


def test_decoded_payload_limit_in_last_base64_group() -> None:
    # 256 KiB is not a multiple of three; the final base64 group can encode
    # one or two excess bytes without exceeding the encoded-length bound.
    with pytest.raises(MarkerError, match="256 KiB"):
        parse_svg(envelope(b"x" * (MAX_PAYLOAD_BYTES + 1)))


def test_xml_depth_limit() -> None:
    nested = b"<g>" * MAX_XML_DEPTH + b"</g>" * MAX_XML_DEPTH
    with pytest.raises(MarkerError, match="nesting limit"):
        parse_svg(envelope().replace(b"</svg>", nested + b"</svg>"))


def test_xml_element_limit() -> None:
    with pytest.raises(MarkerError, match="element or nesting"):
        parse_svg(envelope().replace(b"</svg>", b"<g/>" * MAX_XML_ELEMENTS + b"</svg>"))


def test_long_namespace_rejected_before_repeated_name_expansion() -> None:
    drawing = b'<g xmlns:x="' + b"a" * 257 + b'"><x:t/></g>'
    with pytest.raises(MarkerError, match="namespace"):
        parse_svg(envelope().replace(b"</svg>", drawing + b"</svg>"))


def test_write_node_and_depth_limits_before_text_serialization() -> None:
    many = tuple(Node(str(i), str(i), "file") for i in range(10_000))
    with pytest.raises(MarkerError, match="row limit"):
        render_svg_metadata(Document(Node(".", "", "dir", many)))
    node = Node("leaf", "leaf", "file")
    for _ in range(129):
        node = Node("dir", "dir", "dir", (node,))
    with pytest.raises(MarkerError, match="depth limit"):
        render_svg_metadata(Document(node))


def test_write_payload_limit() -> None:
    document = Document(Node(".", "", "dir", annotation="x" * MAX_PAYLOAD_BYTES))
    with pytest.raises(MarkerError, match="256 KiB"):
        render_svg(document)


def test_whole_rendered_file_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    from treestamp import svg

    # The final drawing can exceed the file cap independently of the payload.
    monkeypatch.setattr(svg, "_drawing", lambda *_: " " * MAX_SVG_BYTES)
    with pytest.raises(MarkerError, match="1 MiB"):
        render_svg(Document(Node(".", "", "dir")))
