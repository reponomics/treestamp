"""Check or regenerate README style previews from its one managed treestamp."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import replace
from pathlib import Path

from treestamp.codec import render_tree_with_paths
from treestamp.document import ATTRIBUTION, Document, parse_document
from treestamp.errors import MarkerError

ROOT = Path(__file__).resolve().parents[1]


def render_previews(document: Document) -> str:
    sections = []
    for style, label in (("ascii", "ASCII"), ("list", "list")):
        settings = replace(document.settings, style=style)
        tree, _ = render_tree_with_paths(document.tree, settings, fenced=True)
        if style == "list":
            root, separator, children = tree.partition("\n")
            tree = root + separator + ("\n" + children if children else "")
        footer = f"\n{ATTRIBUTION}\n" if settings.attribution else ""
        sections.append(
            f"<details>\n<summary>View {label} style</summary>\n\n"
            f"{tree}{footer}\n</details>\n"
        )
    return "\n".join(sections)


def refreshed_content(content: bytes) -> bytes:
    document = parse_document(content)
    starts = list(re.finditer(rb"(?m)^<!-- readme-styles:start -->\r?\n", content))
    ends = list(re.finditer(rb"(?m)^<!-- readme-styles:end -->\r?$", content))
    if len(starts) != 1 or len(ends) != 1 or starts[0].end() > ends[0].start():
        raise ValueError("expected one ordered pair of readme-styles markers")
    start, end = starts[0], ends[0]
    eol = b"\r\n" if start.group().endswith(b"\r\n") else b"\n"
    previews = render_previews(document).encode("utf-8").replace(b"\n", eol)
    return content[: start.end()] + previews + content[end.start() :]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="refresh the previews")
    parser.add_argument("document", nargs="?", type=Path, default=ROOT / "README.md")
    args = parser.parse_args(argv)
    try:
        original = args.document.read_bytes()
        updated = refreshed_content(original)
        if updated == original:
            print("README style previews are current.")
            return 0
        if args.write:
            args.document.write_bytes(updated)
            print("Updated README style previews.")
            return 0
        print(
            "README style previews are stale; run make readme-update.", file=sys.stderr
        )
        return 1
    except (OSError, ValueError, MarkerError) as exc:
        print(f"README style previews: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
