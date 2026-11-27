"""The Docker image is the only uv pin, and the guard rejects ambiguous pins."""

from __future__ import annotations

import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_toolchain.py"
DIGEST = "a" * 64


def version() -> str:
    return ".".join(str(random.randrange(100)) for _ in range(3))


def image(pin: str) -> str:
    return f"FROM ghcr.io/astral-sh/uv:{pin}@sha256:{DIGEST} AS uv\n"


def run_check(
    root: Path, *args: str, output: Path | None = None
) -> subprocess.CompletedProcess[str]:
    # The suite itself may run in GitHub Actions, so never inherit its output file.
    env = {key: value for key, value in os.environ.items() if key != "GITHUB_OUTPUT"}
    if output is not None:
        env["GITHUB_OUTPUT"] = str(output)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=env,
    )


@pytest.fixture
def pin() -> str:
    return version()


@pytest.fixture
def checkout(tmp_path: Path, pin: str) -> Path:
    (tmp_path / "web").mkdir()
    (tmp_path / "web/Dockerfile").write_text(image(pin), encoding="utf-8")
    return tmp_path


def test_version_comes_from_the_image_despite_comments_and_platform(
    checkout: Path, pin: str
) -> None:
    (checkout / "web/Dockerfile").write_text(
        f"# FROM ghcr.io/astral-sh/uv:{version()} AS uv\n"
        + image(pin).replace("FROM ", "  FROM --platform=linux/arm64 ").rstrip()
        + " # pinned\nFROM python:3.11-slim AS base\n",
        encoding="utf-8",
    )
    result = run_check(checkout, "--print-version")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == pin


def test_check_publishes_the_version_as_a_step_output(
    checkout: Path, pin: str, tmp_path: Path
) -> None:
    output = tmp_path / "github-output"
    output.write_text("earlier=value\n", encoding="utf-8")
    result = run_check(checkout, output=output)
    assert result.returncode == 0, result.stderr
    assert output.read_text(encoding="utf-8").splitlines() == [
        "earlier=value",
        f"version={pin}",
    ]


def test_other_tool_pins_may_remain(checkout: Path, pin: str) -> None:
    (checkout / ".tool-versions").write_bytes(b"# tools\r\nactionlint 1.0.0\r\n")
    result = run_check(checkout, "--print-version")
    assert result.stdout.strip() == pin


@pytest.mark.parametrize("entry", ["uv {pin}", "  uv\t{pin}  # pinned", "UV {pin}"])
def test_a_second_uv_pin_is_rejected(checkout: Path, pin: str, entry: str) -> None:
    (checkout / ".tool-versions").write_text(
        f"actionlint 1.0.0\n{entry.format(pin=pin)}\n", encoding="utf-8"
    )
    result = run_check(checkout)
    assert result.returncode == 1
    assert ".tool-versions" in result.stderr


@pytest.mark.parametrize(
    "dockerfile",
    [
        "FROM python:3.11 AS base\n",
        image("1.2.3") + image("latest"),
        image("latest"),
        image("1.2.3rc1"),
        image("1.2.3").replace(f"@sha256:{DIGEST}", ""),
        image("1.2.3").replace(DIGEST, "a" * 63),
        image("1.2.3").replace(DIGEST, "g" * 64),
        image("1.2.3").replace(" AS uv", " AS another_stage"),
    ],
)
def test_missing_ambiguous_or_unpinned_image_fails(
    checkout: Path, dockerfile: str
) -> None:
    (checkout / "web/Dockerfile").write_text(dockerfile, encoding="utf-8")
    result = run_check(checkout, "--print-version")
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Dockerfile" in result.stderr


def test_missing_dockerfile_is_an_error(checkout: Path) -> None:
    (checkout / "web/Dockerfile").unlink()
    result = run_check(checkout)
    assert result.returncode == 1
    assert "Dockerfile" in result.stderr
    assert "Traceback" not in result.stderr
