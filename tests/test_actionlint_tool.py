"""Tool installation rejects unverified or mismatched binaries before replacement."""

from __future__ import annotations

import importlib.util
import io
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/actionlint_tool.py"
spec = importlib.util.spec_from_file_location("actionlint_tool", SCRIPT)
assert spec is not None and spec.loader is not None
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
VERSION = "1.7.12"


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
@pytest.mark.parametrize(
    ("machine", "arch"),
    [("x86_64", "amd64"), ("AMD64", "amd64"), ("aarch64", "arm64"), ("arm64", "arm64")],
)
def test_platform_archive(system: str, machine: str, arch: str) -> None:
    assert tool.archive_name(VERSION, system, machine) == (
        f"actionlint_{VERSION}_{system.lower()}_{arch}.tar.gz"
    )


@pytest.mark.parametrize(
    ("system", "machine"), [("Windows", "AMD64"), ("Linux", "i686")]
)
def test_unsupported_platform(system: str, machine: str) -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        tool.archive_name(VERSION, system, machine)


@pytest.mark.parametrize(
    "pin",
    [
        "",
        "uv 0.13.7\n",
        "actionlint\n",
        "actionlint latest\n",
        "actionlint 1.7\n",
        "actionlint 1.7.12 1.7.11\n",
        "actionlint 1.7.12\nactionlint 1.7.11\n",
    ],
)
def test_pin_must_be_single_exact_version(tmp_path: Path, pin: str) -> None:
    (tmp_path / ".tool-versions").write_text(pin)
    with pytest.raises(ValueError, match="actionlint"):
        tool.read_version(tmp_path)


def test_pin_allows_other_tools_and_comments(tmp_path: Path) -> None:
    (tmp_path / ".tool-versions").write_text(
        "uv 0.13.7\n # actionlint 1.7.11\n actionlint\t1.7.12 # current\n"
    )
    assert tool.read_version(tmp_path) == VERSION


def create_archive(path: Path, kind: bytes = tarfile.REGTYPE) -> None:
    with tarfile.open(path, "w:gz") as bundle:
        member = tarfile.TarInfo("actionlint")
        member.type = kind
        member.linkname = "elsewhere"
        content = b"verified executable"
        member.size = len(content) if kind == tarfile.REGTYPE else 0
        bundle.addfile(member, io.BytesIO(content))


@pytest.mark.parametrize(
    "failure", [None, "download", "attestation", "version", "archive"]
)
def test_install_verifies_before_execution_and_preserves_previous_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    binary = tmp_path / "tools/actionlint"
    binary.parent.mkdir()
    binary.write_bytes(b"previous installation")
    events: list[str] = []

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs.get("check") is True
        if command[1:3] == ["release", "download"]:
            events.append("download")
            assert command[3] == "v1.7.12"
            assert command[command.index("--repo") + 1] == "rhysd/actionlint"
            name = command[command.index("--pattern") + 1]
            assert name == "actionlint_1.7.12_linux_amd64.tar.gz"
            archive = Path(command[command.index("--dir") + 1]) / name
            create_archive(
                archive, tarfile.SYMTYPE if failure == "archive" else tarfile.REGTYPE
            )
        elif command[1:3] == ["attestation", "verify"]:
            events.append("attestation")
            assert command[command.index("--repo") + 1] == "rhysd/actionlint"
            assert command[command.index("--source-ref") + 1] == "refs/tags/v1.7.12"
            assert not (Path(command[-1]).parent / "actionlint").exists()
            assert binary.read_bytes() == b"previous installation"
        else:
            assert events == ["download", "attestation"]
            events.append("version")
            assert command[1:] == ["-version"]
            assert Path(command[0]).read_bytes() == b"verified executable"
            assert binary.read_bytes() == b"previous installation"
            version = "1.7.11" if failure == "version" else VERSION
            return subprocess.CompletedProcess(
                command, 0, stdout=f"{version}\ninstalled by test\n"
            )
        if events[-1] == failure:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(tool.subprocess, "run", run)
    monkeypatch.setattr(tool.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tool.platform, "machine", lambda: "x86_64")
    if failure:
        with pytest.raises((ValueError, subprocess.CalledProcessError)):
            tool.install(str(binary), VERSION, "gh")
        assert binary.read_bytes() == b"previous installation"
    else:
        tool.install(str(binary), VERSION, "gh")
        assert binary.read_bytes() == b"verified executable"
        if os.name != "nt":
            assert binary.stat().st_mode & 0o111
        assert events == ["download", "attestation", "version"]
    assert sorted(path.name for path in binary.parent.iterdir()) == ["actionlint"]


@pytest.mark.parametrize(
    "output",
    [
        "1.7.11\n",
        "v1.7.11\n",
        "",
        "actionlint 1.7.12\n",
        "1.7.12-dev\n",
        "v1.7.12-dev\n",
    ],
)
def test_check_rejects_wrong_or_unrecognized_version(
    monkeypatch: pytest.MonkeyPatch, output: str
) -> None:
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=output),
    )
    with pytest.raises(ValueError, match="expected 1.7.12"):
        tool.check_version("actionlint", VERSION)


@pytest.mark.parametrize("version", ["1.7.12", "v1.7.12"])
def test_check_supports_path_lookup(
    monkeypatch: pytest.MonkeyPatch, version: str
) -> None:
    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert command == ["actionlint", "-version"]
        return subprocess.CompletedProcess(
            command, 0, stdout=f"{version}\nextra information\n"
        )

    monkeypatch.setattr(tool.subprocess, "run", run)
    tool.check_version("actionlint", VERSION)


def test_missing_binary_has_actionable_error(tmp_path: Path) -> None:
    (tmp_path / ".tool-versions").write_text("actionlint 1.7.12\n")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "check",
            "--root",
            str(tmp_path),
            "--binary",
            str(tmp_path / "missing-actionlint"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "make actionlint-install" in result.stderr
    assert "Traceback" not in result.stderr
