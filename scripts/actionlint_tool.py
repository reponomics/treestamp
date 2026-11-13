"""Install an attested actionlint release or check the repository's version pin."""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPOSITORY = "rhysd/actionlint"


def read_version(root: Path) -> str:
    path = root / ".tool-versions"
    entries = [line.split("#", 1)[0].split() for line in path.read_text().splitlines()]
    pins = [entry for entry in entries if entry and entry[0] == "actionlint"]
    if len(pins) != 1 or len(pins[0]) != 2:
        raise ValueError(f"{path}: expected exactly one actionlint version pin")
    version = pins[0][1]
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError(f"{path}: actionlint must use an exact X.Y.Z version")
    return version


def archive_name(version: str, system: str, machine: str) -> str:
    systems = {"Darwin": "darwin", "Linux": "linux"}
    machines = {
        "x86_64": "amd64",
        "amd64": "amd64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    try:
        os_name = systems[system]
        arch = machines[machine.lower()]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported actionlint installation platform: {system}/{machine}; "
            "supported platforms are macOS/Linux on x86_64 or arm64"
        ) from exc
    return f"actionlint_{version}_{os_name}_{arch}.tar.gz"


def check_version(binary: str, version: str) -> None:
    # A relative path containing a slash must stay a path, not become a PATH lookup.
    command = str(Path(binary).resolve()) if os.sep in binary else binary
    result = subprocess.run(
        [command, "-version"], check=True, capture_output=True, text=True
    )
    lines = result.stdout.splitlines()
    actual = lines[0].strip() if lines else "<empty output>"
    if actual.removeprefix("v") != version:
        raise ValueError(f"actionlint version is {actual!r}; expected {version}")


def download_verified(gh: str, version: str, archive: Path) -> None:
    subprocess.run(
        [
            gh,
            "release",
            "download",
            f"v{version}",
            "--repo",
            REPOSITORY,
            "--pattern",
            archive.name,
            "--dir",
            str(archive.parent),
        ],
        check=True,
    )
    subprocess.run(
        [
            gh,
            "attestation",
            "verify",
            "--repo",
            REPOSITORY,
            "--source-ref",
            f"refs/tags/v{version}",
            str(archive),
        ],
        check=True,
    )


def extract_binary(archive: Path, binary: Path) -> None:
    # Read only the expected regular file; never honor archive paths or links.
    with tarfile.open(archive, "r:gz") as bundle:
        members = [
            member for member in bundle.getmembers() if member.name == "actionlint"
        ]
        if len(members) != 1 or not members[0].isfile():
            raise ValueError(
                "actionlint archive must contain one regular actionlint file"
            )
        source = bundle.extractfile(members[0])
        if source is None:
            raise ValueError("actionlint archive contains no executable data")
        with source, binary.open("wb") as output:
            shutil.copyfileobj(source, output)
    binary.chmod(0o755)


def replace_binary(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Stage on the destination filesystem so replacement remains atomic.
    with tempfile.NamedTemporaryFile(
        prefix=".actionlint-", dir=destination.parent, delete=False
    ) as output:
        staged = Path(output.name)
    try:
        shutil.copyfile(source, staged)
        staged.chmod(0o755)
        staged.replace(destination)
    finally:
        staged.unlink(missing_ok=True)


def install(binary: str, version: str, gh: str) -> None:
    name = archive_name(version, platform.system(), platform.machine())
    with tempfile.TemporaryDirectory(prefix="treestamp-actionlint-") as directory:
        temporary = Path(directory)
        archive = temporary / name
        download_verified(gh, version, archive)
        executable = temporary / "actionlint"
        extract_binary(archive, executable)
        check_version(str(executable), version)
        replace_binary(executable, Path(binary).resolve())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("install", "check"))
    parser.add_argument("--binary", required=True)
    parser.add_argument("--gh", default="gh")
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    try:
        version = read_version(args.root)
        if args.command == "install":
            install(args.binary, version, args.gh)
        else:
            check_version(args.binary, version)
    except (
        OSError,
        ValueError,
        tarfile.TarError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"FAIL actionlint: {exc}", file=sys.stderr)
        print(
            "Run make actionlint-install with an authenticated GitHub CLI (gh). "
            "Installation requires successful release attestation verification.",
            file=sys.stderr,
        )
        return 1
    print(f"PASS actionlint {version}: {args.command} ({args.binary})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
