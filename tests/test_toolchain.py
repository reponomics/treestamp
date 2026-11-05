"""The repository guard rejects uv pin drift and incomplete pin updates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_toolchain.py"
DIGEST = "a" * 64
IMAGE = f"FROM ghcr.io/astral-sh/uv:0.13.7@sha256:{DIGEST} AS uv\n"


def run_check(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    (tmp_path / ".tool-versions").write_text("uv 0.13.7\n")
    (tmp_path / "web").mkdir()
    (tmp_path / "web/Dockerfile").write_text(IMAGE)
    return tmp_path


def test_matching_pins_with_comments_whitespace_and_other_tools(checkout: Path) -> None:
    (checkout / ".tool-versions").write_bytes(
        b"# tools\r\nnodejs 24.22.1\r\n  uv\t0.13.7  # pinned\r\n"
    )
    (checkout / "web/Dockerfile").write_text(
        "# FROM ghcr.io/astral-sh/uv:old AS uv\n"
        + IMAGE.replace("FROM ", "  FROM --platform=linux/arm64 ").rstrip()
        + " # pinned\nFROM python:3.11-slim AS base\n"
    )
    result = run_check(checkout)
    assert result.returncode == 0, result.stderr
    assert "both pin 0.13.7" in result.stdout


@pytest.mark.parametrize("changed_file", [".tool-versions", "web/Dockerfile"])
def test_updating_only_one_pin_fails_with_both_versions(
    checkout: Path, changed_file: str
) -> None:
    path = checkout / changed_file
    path.write_text(path.read_text().replace("0.13.7", "0.13.8"))
    result = run_check(checkout)
    assert result.returncode == 1
    assert "uv pins differ" in result.stderr
    assert "0.13.7" in result.stderr and "0.13.8" in result.stderr
    assert "together" in result.stderr


@pytest.mark.parametrize(
    "tools",
    [
        "",
        "python 3.11\n",
        "uv\n",
        "uv latest\n",
        "UV 0.13.7\n",
        "uv >=0.13.7\n",
        "uv 0.13.7rc1\n",
        "uv 0.13.7 0.13.8\n",
        "uv 0.13.7\nuv latest\n",
    ],
)
def test_missing_ambiguous_or_floating_tool_pin_fails(
    checkout: Path, tools: str
) -> None:
    (checkout / ".tool-versions").write_text(tools)
    result = run_check(checkout)
    assert result.returncode == 1
    assert ".tool-versions" in result.stderr


@pytest.mark.parametrize(
    "dockerfile",
    [
        "FROM python:3.11 AS base\n",
        IMAGE + IMAGE.replace("0.13.7", "latest"),
        IMAGE.replace("0.13.7", "latest"),
        IMAGE.replace("0.13.7", "0.13.8rc1"),
        IMAGE.replace(f"@sha256:{DIGEST}", ""),
        IMAGE.replace(DIGEST, "a" * 63),
        IMAGE.replace(DIGEST, "g" * 64),
        IMAGE.replace(" AS uv", " AS another_stage"),
    ],
)
def test_missing_ambiguous_or_unpinned_image_fails(
    checkout: Path, dockerfile: str
) -> None:
    (checkout / "web/Dockerfile").write_text(dockerfile)
    result = run_check(checkout)
    assert result.returncode == 1
    assert "Dockerfile" in result.stderr


@pytest.mark.parametrize("missing", [".tool-versions", "web/Dockerfile"])
def test_missing_input_is_an_error(checkout: Path, missing: str) -> None:
    (checkout / missing).unlink()
    result = run_check(checkout)
    assert result.returncode == 1
    assert Path(missing).name in result.stderr
    assert "Traceback" not in result.stderr
