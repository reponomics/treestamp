"""Exercise headless and interactive artifact installations outside the checkout."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def run(args: list[str], cwd: Path, expected: int = 0) -> str:
    environment = {
        key: value for key, value in os.environ.items() if key != "PYTHONPATH"
    }
    result = subprocess.run(
        args, cwd=cwd, env=environment, capture_output=True, encoding="utf-8"
    )
    if result.returncode != expected:
        raise RuntimeError(
            f"{args!r}: expected {expected}, got {result.returncode}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def _tool(environment: Path, name: str) -> Path:
    """A fresh environment's console scripts: `bin` on POSIX, `Scripts` on Windows."""
    if os.name == "nt":
        return environment / "Scripts" / f"{name}.exe"
    return environment / "bin" / name


def _environment(work: Path) -> Path:
    """Bootstrap with the caller's patched pip instead of ensurepip's old bundle."""
    environment = work / "venv"
    venv.EnvBuilder(with_pip=False).create(environment)
    python = _tool(environment, "python")
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "--python",
            str(python),
            "install",
            "pip>=26.2.2",
        ],
        work,
    )
    return python


def journey(artifact: Path, work: Path) -> None:
    python = _environment(work)
    environment = work / "venv"
    command = [str(_tool(environment, "treestamp"))]
    run([str(python), "-m", "pip", "install", "--no-deps", str(artifact)], work)
    repo = work / "repo"
    repo.mkdir()
    run(["git", "init", "-q", str(repo)], work)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hello')\n")
    (repo / "README.md").write_text(
        "# Fixture\n\n<!-- treestamp:start -->\n```text\n.\n"
        "└── src/ (99 files)\n```\n<!-- treestamp:end -->\n",
        encoding="utf-8",
    )
    run(["git", "add", "."], repo)
    run([*command, "--help"], repo)
    installed_version = run(
        [
            str(python),
            "-c",
            "from importlib.metadata import version; print(version('treestamp'))",
        ],
        repo,
    ).strip()
    assert (
        run([*command, "--version"], repo).strip() == f"treestamp {installed_version}"
    )
    assert "src/ (1 file)" in run([*command, "--print"], repo)
    run([*command, "check"], repo, 1)
    run([*command, "update"], repo)
    run([*command, "check"], repo)
    run([*command, "check"], repo / "src")
    run([*command, "check", "../README.md"], repo / "src")
    run([*command, "check", "repo/README.md"], work)
    assert "src/" in run([*command, "--load", "repo/README.md", "--print"], work)
    assert "src/" in run([*command, "--load", str(repo / "README.md"), "--print"], work)
    run([*command, str(repo), "--print"], work, 2)
    run([*command, "--document", "README.md", "--print"], repo, 2)
    first = (repo / "README.md").read_bytes()
    (repo / "src" / "extra.py").write_text("# new\n")
    run(["git", "add", "src/extra.py"], repo)
    run([*command, "check"], repo, 1)
    assert (repo / "README.md").read_bytes() == first
    run([*command, "update"], repo)
    run([*command, "check"], repo)
    run(
        [
            str(python),
            "-c",
            "import importlib.util; assert importlib.util.find_spec('textual') is None",
        ],
        repo,
    )
    assert "textual" not in run(
        [
            str(python),
            "-c",
            "import sys; import treestamp.cli; print(list(sys.modules))",
        ],
        repo,
    )
    print(
        f"PASS {artifact.name}: print, check drift, update, "
        "idempotence, headless installation"
    )


def editor_journey(artifact: Path, work: Path) -> None:
    python = _environment(work)
    environment = work / "venv"
    command = [str(_tool(environment, "treestamp"))]
    run([str(python), "-m", "pip", "install", str(artifact)], work)
    repo = work / "repo"
    repo.mkdir()
    run(["git", "init", "-q", str(repo)], work)
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hello')\n")
    (repo / "src" / "internal.py").write_text("# hidden in the editor\n")
    document = repo / "README.md"
    document.write_text(
        "# Fixture\n\n<!-- treestamp:start -->\n```text\n.\n"
        "└── src/ (99 files)\n```\n<!-- treestamp:end -->\n",
        encoding="utf-8",
    )
    run(["git", "add", "."], repo)
    driver = work / "editor_check.py"
    driver.write_bytes(
        Path(__file__).with_name("installed_editor_check.py").read_bytes()
    )
    run([str(python), str(driver)], repo)
    saved = document.read_bytes()
    run([*command, "check"], repo)
    assert document.read_bytes() == saved
    print(
        f"PASS {artifact.name}: normal installation, installed editor "
        "expansion/hiding/annotation/write, installed check"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    args = parser.parse_args()
    artifacts = sorted([*args.dist.glob("*.whl"), *args.dist.glob("*.tar.gz")])
    if len(artifacts) != 2:
        raise RuntimeError(
            "expected exactly one wheel and one sdist; clean dist then build"
        )
    for artifact in artifacts:
        with tempfile.TemporaryDirectory(prefix="treestamp-install-") as temporary:
            journey(artifact.resolve(), Path(temporary).resolve())
        with tempfile.TemporaryDirectory(prefix="treestamp-editor-") as temporary:
            editor_journey(artifact.resolve(), Path(temporary).resolve())


if __name__ == "__main__":
    main()
