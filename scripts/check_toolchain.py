"""Read the uv version pinned by the Docker image, the single uv pin.

Dependabot maintains the image reference, so local checks and CI read the
version from it instead of keeping a second copy in .tool-versions.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

VERSION = r"[0-9]+\.[0-9]+\.[0-9]+"
DOCKERFILE = "web/Dockerfile"
IMAGE = r"FROM\s+(?:--platform=\S+\s+)?ghcr\.io/astral-sh/uv"


def _entries(path: Path, pattern: str) -> list[str]:
    lines = [
        line.split("#", 1)[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    return [line for line in lines if re.match(pattern, line, re.IGNORECASE)]


def read_version(root: Path) -> str:
    """Require exactly one digest-pinned uv stage and no competing pin."""
    path = root / DOCKERFILE
    entries = _entries(path, rf"{IMAGE}\b")
    if len(entries) != 1:
        raise ValueError(f"{path}: expected exactly one uv image; found {len(entries)}")
    match = re.fullmatch(
        rf"{IMAGE}:({VERSION})@sha256:[0-9a-f]{{64}}\s+AS\s+uv",
        entries[0],
        re.IGNORECASE,
    )
    if match is None:
        raise ValueError(f"{path}: invalid uv image pin: {entries[0]!r}")
    tools = root / ".tool-versions"
    if tools.exists() and _entries(tools, r"uv\b"):
        raise ValueError(
            f"{tools}: remove the uv entry; {DOCKERFILE} is the only uv pin"
        )
    return match.group(1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--print-version", action="store_true", help="print only the version"
    )
    args = parser.parse_args()
    try:
        version = read_version(args.root)
    except (OSError, ValueError) as exc:
        print(f"FAIL uv toolchain: {exc}", file=sys.stderr)
        return 1
    if args.print_version:
        print(version)
        return 0
    # In GitHub Actions, expose the version to setup-uv as steps.<id>.outputs.version.
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"version={version}\n")
    print(f"PASS uv toolchain: {DOCKERFILE} pins {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
