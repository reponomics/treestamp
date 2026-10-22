"""Check retained documentation's local destinations without fetching URLs."""

from __future__ import annotations

import argparse
import re
import subprocess
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)")
REFERENCE = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)", re.MULTILINE)
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def prose(source: str) -> str:
    """Ignore fenced examples while retaining line numbers for diagnostics."""
    fence: str | None = None
    lines: list[str] = []
    for line in source.splitlines(keepends=True):
        match = FENCE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker.startswith(fence):
                fence = None
            lines.append("\n")
        else:
            lines.append("\n" if fence else line)
    return "".join(lines)


class HtmlLinks(HTMLParser):
    """Collect actual HTML link/image/media destinations."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key in {"href", "src", "poster"} and value is not None:
                self.links.append((self.getpos()[0], value))


def destinations(source: str) -> list[tuple[int, str]]:
    result = [
        (source.count("\n", 0, match.start()) + 1, match.group(1).strip("<>"))
        for pattern in (MARKDOWN_LINK, REFERENCE)
        for match in pattern.finditer(source)
    ]
    parser = HtmlLinks()
    parser.feed(source)
    return result + parser.links


def canonical_path(url: str) -> str | None:
    """Map this project's main-branch URLs to files in the candidate checkout."""
    parts = urlsplit(url)
    prefix = "/reponomics/treestamp/"
    if not parts.path.startswith(prefix):
        return None
    path = parts.path.removeprefix(prefix)
    if parts.netloc == "raw.githubusercontent.com" and path.startswith("main/"):
        return path.removeprefix("main/")
    if parts.netloc == "github.com":
        for marker in ("blob/main/", "tree/main/", "raw/main/"):
            if path.startswith(marker):
                return path.removeprefix(marker)
    return None


def target_path(source: Path, url: str) -> Path | None:
    canonical = canonical_path(url)
    if canonical is not None:
        return ROOT / unquote(canonical)
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path:
        return None
    path = unquote(parts.path)
    if path.startswith("/static/"):
        return ROOT / "web/src/treestamp_web" / path.lstrip("/")
    if path.startswith("/"):
        return None  # Application routes, not checkout-relative references.
    return source.parent / path


def check(path: Path) -> list[str]:
    failures: list[str] = []
    for line, url in destinations(prose(path.read_text(encoding="utf-8"))):
        target = target_path(path, url)
        if target is not None and not target.exists():
            failures.append(f"{path}:{line}: missing {url}")
        parts = urlsplit(url)
        if path == ROOT / "README.md" and parts.path and not parts.scheme:
            failures.append(
                f"README.md:{line}: package description needs an absolute URL: {url}"
            )
    return failures


def tracked_documents() -> list[Path]:
    output = subprocess.check_output(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.md",
            "*.html",
        ],
        cwd=ROOT,
    )
    return sorted({ROOT / name.decode() for name in output.split(b"\0") if name})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", type=Path, nargs="*")
    args = parser.parse_args()
    paths = [path.resolve() for path in args.paths] or tracked_documents()
    if args.paths and any(not path.is_file() for path in paths):
        parser.error("each explicit path must name an existing document")
    existing = [path for path in paths if path.is_file()]
    failures = [failure for path in existing for failure in check(path)]
    if failures:
        print("\n".join(failures))
        return 1
    print(
        f"PASS {len(existing)} documents: local destinations and canonical README URLs"
    )
    print("External availability and fragment anchors require separate review.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
