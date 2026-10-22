"""Verify both repository hook entries through a real pre-commit installation."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


def run(args: list[str], cwd: Path, expected: int = 0) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, encoding="utf-8")
    if result.returncode != expected:
        raise RuntimeError(
            f"{args!r}: expected {expected}, got {result.returncode}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result.stdout


def main() -> None:
    source = Path(__file__).resolve().parents[1]
    revision = run(["git", "rev-parse", "HEAD"], source).strip()
    with tempfile.TemporaryDirectory(prefix="treestamp-hooks-") as temporary:
        repo = Path(temporary)
        run(["git", "init", "-q"], repo)
        run(["git", "config", "user.name", "Acceptance"], repo)
        run(["git", "config", "user.email", "acceptance@example.invalid"], repo)
        (repo / "src").mkdir()
        (repo / "src" / "app.py").write_text("# tracked source\n")
        document = repo / "README.md"
        document.write_text(
            "<!-- treestamp:start -->\n```text\n.\n"
            "└── src/ (99 files)\n```\n<!-- treestamp:end -->\n",
            encoding="utf-8",
        )
        (repo / ".pre-commit-config.yaml").write_text(
            f"repos:\n  - repo: {json.dumps(str(source))}\n"
            f"    rev: {revision}\n    hooks:\n"
            "      - id: treestamp-check\n      - id: treestamp\n"
        )
        run(["git", "add", "."], repo)
        hook = [sys.executable, "-m", "pre_commit", "run"]
        before = document.read_bytes()
        run([*hook, "treestamp-check", "--all-files"], repo, 1)
        assert document.read_bytes() == before
        # The updating hook succeeds as a CLI but pre-commit reports modified files.
        run([*hook, "treestamp", "--all-files"], repo, 1)
        assert document.read_bytes() != before
        run(["git", "add", "README.md"], repo)
        run([*hook, "treestamp-check", "--all-files"], repo)
        # Signing is the developer's setting; this commit must not wait on a key.
        run(["git", "-c", "commit.gpgSign=false", "commit", "-qm", "curated"], repo)
        (repo / "src" / "new.py").write_text("# source-only change\n")
        run(["git", "add", "src/new.py"], repo)
        run([*hook, "treestamp-check"], repo, 1)
        run([*hook, "treestamp"], repo, 1)
        run(["git", "add", "README.md"], repo)
        run([*hook, "treestamp-check"], repo)
        run([*hook, "treestamp"], repo)
        print(
            "PASS repository hooks: drift, no-write check, update, restage, "
            "source-only change"
        )


if __name__ == "__main__":
    main()
