"""Paired SVG artifact boundary with independent metadata and visual styles."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

from treestamp.errors import MarkerError
from treestamp.svg_layout import LAYOUT_STYLES, Layout, display_text
from treestamp.svg_metadata import (
    MAX_SVG_BYTES,
    SVG_NAMESPACE,
    SvgAppearance,
    SvgArtifact,
    encode_metadata,
    prepare_metadata,
    read_metadata,
)

if TYPE_CHECKING:
    from treestamp.document import Document

__all__ = [
    "SvgAppearance",
    "SvgArtifact",
    "parse_svg",
    "render_svg",
    "render_svg_metadata",
    "render_svg_variants",
]

_DEFAULT_APPEARANCE = SvgAppearance()

# The image has no background. Appearance chooses only its foreground ink.
_INK = {"adaptive": "#000000", "light": "#000000", "dark": "#ffffff"}
# Fixed author-controlled CSS only; labels and imported markup cannot supply rules.
# No color-scheme override here: the embedding image supplies the preferred scheme.
_ADAPTIVE_STYLE = """<style>
  text { fill: #000000; }
  g[stroke] { stroke: #000000; }
  @media (prefers-color-scheme: dark) {
    text { fill: #ffffff; }
    g[stroke] { stroke: #ffffff; }
  }
</style>"""


def parse_svg(content: bytes) -> SvgArtifact:
    """Recover embedded data; incoming drawing markup is deliberately discarded."""
    artifact = read_metadata(content)
    if artifact.appearance.style not in LAYOUT_STYLES:
        unknown = artifact.appearance.style
        return replace(
            artifact,
            appearance=replace(artifact.appearance, style="continuous"),
            warnings=(f"SVG style {unknown!r} is unavailable; using continuous.",),
        )
    return artifact


def _bounded(content: str) -> str:
    if len(content.encode("utf-8")) > MAX_SVG_BYTES:
        raise MarkerError("SVG exceeds the 1 MiB file limit")
    return content


def render_svg_metadata(
    document: Document, appearance: SvgAppearance = _DEFAULT_APPEARANCE
) -> str:
    """Transport envelope for a document baseline; not a graphical preview."""
    return _bounded(
        f'<svg xmlns="{SVG_NAMESPACE}">{encode_metadata(document, appearance)}</svg>\n'
    )


def render_svg(
    document: Document,
    appearance: SvgAppearance = _DEFAULT_APPEARANCE,
    newline: str = "\n",
) -> str:
    """Generate deterministic standalone SVG from validated accepted tree data."""
    style = LAYOUT_STYLES.get(appearance.style)
    if style is None:
        raise MarkerError(f"unsupported SVG visual style: {appearance.style!r}")
    metadata = encode_metadata(document, appearance)
    layout = style(document)
    return _serialize_svg(metadata, layout, appearance, newline)


def render_svg_variants(
    document: Document, style: str = "continuous"
) -> dict[str, str]:
    """Produce complete appearances with one metadata preparation and layout."""
    appearance = SvgAppearance(style=style)
    layout_style = LAYOUT_STYLES.get(appearance.style)
    if layout_style is None:
        raise MarkerError(f"unsupported SVG visual style: {style!r}")
    metadata = prepare_metadata(document)
    layout = layout_style(document)
    variants = {}
    for theme in _INK:
        variant = replace(appearance, theme=theme)
        variants[theme] = _serialize_svg(metadata.render(variant), layout, variant)
    return variants


def _serialize_svg(
    metadata: str, layout: Layout, appearance: SvgAppearance, newline: str = "\n"
) -> str:
    """Rendered line breaks are all structural, so any newline style is safe."""
    drawing = _drawing(layout, appearance)
    text = (
        f'<svg xmlns="{SVG_NAMESPACE}" width="{layout.width}" '
        f'height="{layout.height}" viewBox="0 0 {layout.width} {layout.height}" '
        'role="img" aria-labelledby="title description">\n'
        '<title id="title">Repository tree</title>\n'
        '<desc id="description">Directory structure and annotations. '
        "Editable treestamp data is embedded in this image.</desc>\n"
        f"{metadata}\n{drawing}\n</svg>\n"
    )
    return _bounded(text.replace("\n", newline))


def _drawing(layout: Layout, appearance: SvgAppearance) -> str:
    foreground = _INK[appearance.theme]
    parts = [_ADAPTIVE_STYLE] if appearance.theme == "adaptive" else []
    parts.append(
        f'<g fill="none" stroke="{foreground}" stroke-opacity="0.4" '
        'stroke-width="1.25">'
    )
    for line in layout.branches:
        parts.append(
            f'<line x1="{line.x1}" y1="{line.y1}" x2="{line.x2}" y2="{line.y2}"/>'
        )
    parts.append(
        '</g>\n<g font-family="monospace" font-size="14" xml:space="preserve">'
    )
    for run in layout.labels:
        opacity = "0.65" if run.role == "note" else "1"
        weight = "600" if run.role == "directory" else "400"
        parts.append(
            f'<text x="{run.x}" y="{run.y}" fill="{foreground}" '
            f'fill-opacity="{opacity}" font-weight="{weight}">'
            f"{escape(display_text(run.text))}</text>"
        )
    parts.append("</g>")
    return "\n".join(parts)
