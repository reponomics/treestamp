"""Try the manual placement view in a disposable repository."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from treestamp.document import write_document
from treestamp.editor import EditorController
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings
from treestamp.tui import TreestampApp


def git(repository: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repository), *args], check=True, capture_output=True
    )


def prepare(repository: Path) -> EditorController:
    git(repository, "init", "-q")
    paths = (
        "docs/start.md",
        "docs/reference.md",
        "src/legacy.py",
        "src/retired.py",
        "src/main.py",
        "src/tools/check.py",
        "tools/report.py",
        "tools/formats/csv.py",
        "tools/formats/json.py",
        "README.md",
    )
    for path in paths:
        file = repository / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(f"Example: {path}\n")
    git(repository, "add", ".")
    editor = EditorController(capture_snapshot(repository), Settings())
    session = editor.state.session
    for path in ("docs", "src", "tools", "tools/formats"):
        session.expand(path)
    for path, note in {
        "docs/start.md": "A short guide for new contributors",
        "src/legacy.py": "Import records from the previous format",
        "src/retired.py": "Retired compatibility layer — this one can be skipped",
        "tools": "Reporting utilities",
        "tools/report.py": "Generate the monthly report",
        "tools/formats/csv.py": "Read comma-separated report data",
    }.items():
        session.set_annotation(path, note)
    write_document(editor.document(), repository / "tree.md", create=True)
    for source, target in (
        ("docs/start.md", "docs/guide.md"),
        ("src/legacy.py", "src/importers.py"),
        ("tools/report.py", "src/tools/report.py"),
        ("tools/formats", "src/tools/formats"),
    ):
        git(repository, "mv", source, target)
    git(repository, "rm", "-f", "src/retired.py")
    editor.adopt(editor.prepare_load("tree.md"))
    return editor


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="treestamp-relink-") as directory:
        editor = prepare(Path(directory).resolve())
        TreestampApp(editor).run()


if __name__ == "__main__":
    main()
