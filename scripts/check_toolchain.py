"""Reject drift between the development/CI and Docker uv pins."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

VERSION = r"[0-9]+\.[0-9]+\.[0-9]+"


def read_pin(path: Path, entry_pattern: str, pin_pattern: str, flags: int = 0) -> str:
    """Require one entry before validating its exact version and syntax."""
    lines = [line.split("#", 1)[0].strip() for line in path.read_text().splitlines()]
    entries = [line for line in lines if re.match(entry_pattern, line, re.IGNORECASE)]
    if len(entries) != 1:
        raise ValueError(f"{path}: expected exactly one uv pin; found {len(entries)}")
    match = re.fullmatch(pin_pattern, entries[0], flags)
    if match is None:
        raise ValueError(f"{path}: invalid uv pin: {entries[0]!r}")
    return match.group(1)


def check(root: Path) -> str:
    development = read_pin(root / ".tool-versions", r"uv\b", rf"uv\s+({VERSION})")
    docker = read_pin(
        root / "web/Dockerfile",
        r"FROM\s+(?:--platform=\S+\s+)?ghcr\.io/astral-sh/uv\b",
        rf"FROM\s+(?:--platform=\S+\s+)?ghcr\.io/astral-sh/uv:({VERSION})"
        r"@sha256:[0-9a-f]{64}\s+AS\s+uv",
        flags=re.IGNORECASE,
    )
    if development != docker:
        raise ValueError(
            f"uv pins differ: .tool-versions={development}, web/Dockerfile={docker}. "
            "Update .tool-versions and the Docker image version/digest together."
        )
    return development


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    try:
        version = check(args.root)
    except (OSError, ValueError) as exc:
        print(f"FAIL uv toolchain: {exc}", file=sys.stderr)
        return 1
    print(f"PASS uv toolchain: .tool-versions and web/Dockerfile both pin {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
