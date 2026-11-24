"""Semantic SVG conversions use the text codec, independently of drawing style."""

import base64
from dataclasses import FrozenInstanceError, replace
from xml.etree import ElementTree as ET

import pytest

from treestamp.document import Document, parse_document, render_region
from treestamp.errors import MarkerError
from treestamp.model import Node, Settings
from treestamp.svg import (
    SvgAppearance,
    parse_svg,
    render_svg,
    render_svg_metadata,
)
from treestamp.svg_layout import LAYOUT_STYLES, Layout, TextRun
from treestamp.svg_metadata import (
    PAYLOAD_NAMESPACE,
    SVG_NAMESPACE,
    apply_text_preferences,
)


def sample(style: str = "unicode") -> Document:
    nodes = (
        Node(
            "src",
            "src",
            "dir",
            (Node("main.py", "src/main.py", "file", annotation="Main entry"),),
        ),
        Node("folded", "folded", "dir", files=3, dirs=2),
        Node("link", "link", "symlink", target="src/main.py", annotation="Shortcut"),
        Node("unknown", "unknown", "symlink"),
        Node("vendor", "vendor", "gitlink"),
        Node(
            "a  # b -> c [gitlink]",
            "a  # b -> c [gitlink]",
            "file",
            annotation="Real note",
        ),
        Node("byte\udcff", "byte\udcff", "file"),
    )
    return Document(
        Node(".", "", "dir", nodes, annotation="A scoped tree"),
        Settings(root="package", style=style, attribution=True),
        frozenset({"package/secret"}),
    )


@pytest.mark.parametrize("style", ["unicode", "ascii"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_all_kinds_paths_counts_scope_hiding_round_trip(style: str, theme: str) -> None:
    document = sample(style)
    svg = render_svg(document, SvgAppearance(theme=theme))
    artifact = parse_svg(svg.encode())
    assert artifact.document == document
    assert artifact.appearance == SvgAppearance(theme=theme)
    assert artifact.warnings == ()
    assert render_svg(artifact.document, artifact.appearance) == svg
    metadata = ET.fromstring(svg).find(
        f"{{{SVG_NAMESPACE}}}metadata/{{{PAYLOAD_NAMESPACE}}}treestamp"
    )
    assert metadata is not None
    assert base64.b64decode(metadata.text or "") == render_region(document).encode(
        "utf-8", "surrogateescape"
    )


@pytest.mark.parametrize("style", ["unicode", "ascii"])
@pytest.mark.parametrize("counts", [True, False])
def test_unobservable_preferences_are_retained(style: str, counts: bool) -> None:
    document = Document(Node(".", "", "dir"), Settings(style=style, show_counts=counts))
    assert parse_svg(render_svg_metadata(document).encode()).document == document


def test_fidelity_uses_text_normalizations() -> None:
    document = Document(
        Node(
            ".",
            "",
            "dir",
            (Node("zero", "zero", "dir", files=0),),
            annotation="Tabs\there",
        )
    )
    expected = parse_document(render_region(document).encode())
    expected = replace(expected, settings=document.settings)
    assert parse_svg(render_svg(document).encode()).document == expected


def test_visible_edit_is_ignored_and_not_reexported() -> None:
    document = sample()
    svg = render_svg(document)
    edited = svg.replace("Main entry", "Forged description").replace(
        "</svg>",
        '<script>unsafe()</script><image href="https://invalid.example/no-fetch"/></svg>',
    )
    artifact = parse_svg(edited.encode())
    assert artifact.document == document
    assert render_svg(artifact.document, artifact.appearance) == svg


def test_unknown_visual_style_falls_back_without_losing_data() -> None:
    svg = render_svg(sample()).replace('style="continuous"', 'style="future-style"')
    artifact = parse_svg(svg.encode())
    assert artifact.document == sample()
    assert artifact.appearance == SvgAppearance()
    assert len(artifact.warnings) == 1
    assert "future-style" in artifact.warnings[0]


def test_second_style_reuses_metadata_and_serializer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def second(document: Document) -> Layout:
        return Layout(300, 100, (TextRun(24, 40, document.tree.annotation),), ())

    monkeypatch.setitem(LAYOUT_STYLES, "test-alternate", second)
    appearance = SvgAppearance(style="test-alternate", theme="dark")
    svg = render_svg(sample(), appearance)
    assert "<line" not in svg
    artifact = parse_svg(svg.encode())
    assert artifact.document == sample()
    assert artifact.appearance == appearance
    assert artifact.warnings == ()


def test_unknown_export_style_rejected() -> None:
    with pytest.raises(MarkerError, match="unsupported SVG visual style"):
        render_svg(sample(), SvgAppearance(style="unknown"))


@pytest.mark.parametrize(
    "options",
    [
        {"theme": "auto"},
        {"style": "<script>"},
        {"style": ""},
        {"style": "A"},
        {"style": "a" * 65},
    ],
)
def test_appearance_validation(options: dict[str, str]) -> None:
    with pytest.raises(MarkerError):
        SvgAppearance(**options)


def test_appearance_is_immutable() -> None:
    appearance = SvgAppearance()
    with pytest.raises(FrozenInstanceError):
        appearance.theme = "dark"  # type: ignore[misc]


def test_read_rejects_contradictory_observable_preferences() -> None:
    svg = render_svg(sample())
    with pytest.raises(MarkerError, match="text_style contradicts"):
        parse_svg(svg.replace('text_style="unicode"', 'text_style="ascii"').encode())
    with pytest.raises(MarkerError, match="positive embedded counts"):
        parse_svg(svg.replace('show_counts="true"', 'show_counts="false"').encode())


def test_write_rejects_contradictory_count_preference() -> None:
    document = sample()
    document = replace(document, settings=replace(document.settings, show_counts=False))
    with pytest.raises(MarkerError, match="positive embedded counts"):
        render_svg(document)


def test_shared_text_preferences_validate_boolean_and_restore_ambiguity() -> None:
    document = Document(Node(".", "", "dir"))
    restored = apply_text_preferences(document, "ascii", False)
    assert restored.settings.style == "ascii"
    assert restored.settings.show_counts is False
    with pytest.raises(MarkerError, match="boolean"):
        apply_text_preferences(document, "unicode", 1)  # type: ignore[arg-type]


def test_folds_do_not_invent_descendants_and_hiding_is_only_in_payload() -> None:
    document = Document(
        Node(".", "", "dir", (Node("folded", "folded", "dir", files=2),)),
        hidden=frozenset({"secret"}),
    )
    svg = render_svg(document)
    texts = [
        element.text for element in ET.fromstring(svg).iter(f"{{{SVG_NAMESPACE}}}text")
    ]
    assert texts == ["./", "folded/ (2 files)"]
    assert parse_svg(svg.encode()).document == document


def test_xml_safe_display_preserves_exact_byte_and_control_names() -> None:
    names = [
        "<&>\"'",
        "byte\udcff",
        "line\nbreak",
        "tab\tname",
        "end\uffff",
        "return\rname",
        " bell\x07 ",
    ]
    document = Document(
        Node(".", "", "dir", tuple(Node(name, name, "file") for name in names))
    )
    svg = render_svg(document)
    root = ET.fromstring(svg)
    assert parse_svg(svg.encode()).document == document
    text = " ".join(
        element.text or "" for element in root.iter(f"{{{SVG_NAMESPACE}}}text")
    )
    assert "<&>\"'" in text
    assert "byte\\xff" in text
    assert "line\\x0abreak" in text
    assert "end\\uffff" in text
    allowed = {"svg", "title", "desc", "metadata", "rect", "g", "line", "text"}
    for element in root.iter():
        namespace, local = element.tag[1:].split("}")
        assert namespace == PAYLOAD_NAMESPACE or local in allowed
        assert not any(key.startswith("on") or key == "href" for key in element.attrib)


@pytest.mark.parametrize("theme, ink", [("light", "#000000"), ("dark", "#ffffff")])
def test_transparent_monochrome_image_keeps_notes_on_the_entry_row(theme, ink):
    document = Document(
        Node(
            ".",
            "",
            "dir",
            (Node("file.py", "file.py", "file", annotation="Inline & editable"),),
        )
    )
    source = render_svg(document, SvgAppearance(theme=theme))
    root = ET.fromstring(source)
    assert not list(root.iter(f"{{{SVG_NAMESPACE}}}rect"))
    labels = list(root.iter(f"{{{SVG_NAMESPACE}}}text"))
    assert {label.attrib["fill"] for label in labels} == {ink}
    name = next(label for label in labels if label.text == "file.py")
    note = next(label for label in labels if label.text == "# Inline & editable")
    assert name.attrib["y"] == note.attrib["y"]
    assert float(note.attrib["fill-opacity"]) < float(name.attrib["fill-opacity"])
    assert parse_svg(source.encode()).document == document
