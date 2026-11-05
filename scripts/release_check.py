"""Verify built core artifacts against project metadata and print SHA-256 hashes."""

from __future__ import annotations

import argparse
import hashlib
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from email.message import Message

ROOT = Path(__file__).resolve().parents[1]
SDIST_FILES = {
    "README.md",
    "LICENSE",
    "PRIVACY.md",
    "docs/MAINTENANCE.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "Makefile",
    ".gitignore",
    ".python-version",
    ".pre-commit-config.yaml",
    ".pre-commit-hooks.yaml",
    "scripts/changed_tests.py",
    "scripts/check_docs.py",
    "scripts/distribution_check.py",
    "scripts/hook_check.py",
    "scripts/installed_editor_check.py",
    "scripts/release_check.py",
    "scripts/readme_styles.py",
}


def artifact_metadata(path: Path) -> tuple[bytes, set[str]]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            metadata = [name for name in names if name.endswith(".dist-info/METADATA")]
            if len(metadata) != 1:
                raise ValueError(f"{path.name}: expected one wheel metadata file")
            return archive.read(metadata[0]), names
    with tarfile.open(path) as archive:
        names = {member.name for member in archive.getmembers() if member.isfile()}
        metadata = [
            name
            for name in names
            if name.count("/") == 1 and name.endswith("/PKG-INFO")
        ]
        if len(metadata) != 1:
            raise ValueError(f"{path.name}: expected one top-level PKG-INFO")
        stream = archive.extractfile(metadata[0])
        if stream is None:
            raise ValueError(f"{path.name}: metadata is unreadable")
        return stream.read(), names


def verify_headers(metadata: Message, project: dict[str, object]) -> None:
    expected = {
        "Name": project["name"],
        "Version": project["version"],
        "Requires-Python": project["requires-python"],
        "License-Expression": "MIT",
        "Description-Content-Type": "text/markdown",
    }
    for key, value in expected.items():
        if metadata.get(key) != value:
            raise ValueError(f"{key} does not match project metadata")
    expected_urls = project["urls"]
    if not isinstance(expected_urls, dict):
        raise ValueError("project.urls must be a table")
    actual_urls = set(metadata.get_all("Project-URL", []))
    for label, url in expected_urls.items():
        if f"{label}, {url}" not in actual_urls:
            raise ValueError(f"missing project URL {label}")


def expected_contents(path: Path) -> set[str]:
    """Keep publication boundaries independent of the build configuration."""
    package = {
        item.relative_to(ROOT / "src").as_posix()
        for item in (ROOT / "src/treestamp").glob("*.py")
    } | {"treestamp/py.typed"}
    if path.suffix == ".whl":
        name, version, *_tags = path.stem.split("-")
        metadata = f"{name}-{version}.dist-info"
        return package | {
            f"{metadata}/{item}"
            for item in (
                "METADATA",
                "WHEEL",
                "entry_points.txt",
                "licenses/LICENSE",
                "RECORD",
            )
        }
    tests = {
        item.relative_to(ROOT).as_posix() for item in (ROOT / "tests").glob("*.py")
    }
    files = SDIST_FILES | {f"src/{item}" for item in package} | tests | {"PKG-INFO"}
    prefix = path.name.removesuffix(".tar.gz")
    return {f"{prefix}/{item}" for item in files}


def verify_contents(names: set[str], path: Path) -> None:
    expected = expected_contents(path)
    unexpected = names - expected
    if unexpected:
        raise ValueError(f"unexpected packaged files: {', '.join(sorted(unexpected))}")
    missing = expected - names
    if missing:
        raise ValueError(f"missing packaged files: {', '.join(sorted(missing))}")


def verify(path: Path, project: dict[str, object], readme: str) -> None:
    raw, names = artifact_metadata(path)
    metadata = Parser().parsestr(raw.decode("utf-8"))
    verify_headers(metadata, project)
    payload = metadata.get_payload()
    if not isinstance(payload, str) or payload.strip() != readme.strip():
        raise ValueError("packaged README differs from this checkout")
    verify_contents(names, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    wheels = list(args.dist.glob("*.whl"))
    sources = list(args.dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        parser.error("expected one wheel and one sdist; use a clean output directory")
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for path in wheels + sources:
        try:
            verify(path, project, readme)
        except (ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
            parser.error(str(exc))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        print(f"{digest}  {path.name}")
    print("PASS artifact metadata, README identity, package contents, and license")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
