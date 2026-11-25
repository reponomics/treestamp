"""Stateless SVG export from the accepted textual projection, never session data."""

from __future__ import annotations

from treestamp.document import extract_region, parse_document
from treestamp.errors import MarkerError
from treestamp.svg import SvgAppearance, render_svg_variants
from treestamp.svg_layout import LAYOUT_STYLES
from treestamp.svg_metadata import (
    MAX_PAYLOAD_BYTES,
    MAX_SVG_BYTES,
    apply_text_preferences,
)

# JSON may escape each payload byte as six ASCII characters. This transport
# bound is independent of the much smaller, cache-bound session envelope.
EXPORT_BODY_CAP = 2 * 1024 * 1024
# Three independently bounded SVGs, including worst-case JSON string escaping.
EXPORT_RESPONSE_CAP = 3 * MAX_SVG_BYTES * 6 + 1024


def parse_appearance(value: object) -> SvgAppearance:
    """Accept only registered artifact choices, with no arbitrary renderer options."""
    if not isinstance(value, dict) or set(value) != {"style", "theme"}:
        raise MarkerError("appearance must contain style and theme")
    appearance = SvgAppearance(style=value["style"], theme=value["theme"])
    if appearance.style not in LAYOUT_STYLES:
        raise MarkerError(f"unsupported SVG visual style: {appearance.style!r}")
    return appearance


def export_svg(data: object) -> dict[str, str]:
    """Validate a complete region and its otherwise unobservable preferences."""
    if not isinstance(data, dict) or set(data) != {
        "region",
        "text_style",
        "show_counts",
        "style",
    }:
        raise MarkerError(
            "SVG export requires region, text_style, show_counts, and style"
        )
    appearance = parse_appearance({"style": data["style"], "theme": "auto"})
    region, style, counts = data["region"], data["text_style"], data["show_counts"]
    if (
        not isinstance(region, str)
        or not isinstance(style, str)
        or type(counts) is not bool
    ):
        raise MarkerError("invalid SVG export field types")
    try:
        payload = region.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        raise MarkerError("region contains an unsupported Unicode surrogate") from None
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise MarkerError("SVG textual payload exceeds the 256 KiB limit")
    document = parse_document(payload)
    if extract_region(payload) != payload:
        raise MarkerError("SVG export requires only a complete treestamp region")
    document = apply_text_preferences(document, style, counts)
    return render_svg_variants(document, appearance.style)
