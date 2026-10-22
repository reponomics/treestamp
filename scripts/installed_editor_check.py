"""Drive the installed CLI's real editor; run only inside an artifact test venv."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Input

import treestamp
from treestamp.cli import main
from treestamp.document import load_document
from treestamp.tui import TreestampApp


async def curate(app: TreestampApp) -> bool | None:
    async with app.run_test() as pilot:
        await pilot.press("l", "enter")
        await pilot.pause()
        await pilot.press("down", "right", "right")
        assert app.cursor.path == "src/app.py"
        await pilot.press("a")
        app.screen.query_one("#prompt-input", Input).value = "Application entry point"
        await pilot.press("enter", "down")
        assert app.cursor.path == "src/internal.py"
        await pilot.press("h", "w")
        field = app.screen.query_one("#prompt-input", Input)
        assert field.value == "README.md"
        await pilot.press("enter")
        await pilot.pause()
        assert not app.editor.dirty
        await pilot.press("q")
    return app.return_value


def run_editor(app: TreestampApp) -> bool | None:
    return asyncio.run(curate(app))


def verify() -> None:
    assert treestamp.__file__ is not None
    assert Path(treestamp.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    # Keep CLI dispatch and the real editor intact; replace only the terminal runner.
    with patch.object(TreestampApp, "run", run_editor):
        assert main(["--document", "README.md"]) == 0
    document, _ = load_document(Path("README.md"))
    assert document is not None
    rows = {node.path: node for node in document.tree.walk()}
    assert rows["src/app.py"].annotation == "Application entry point"
    assert "src/internal.py" not in rows
    assert "src/internal.py" in document.hidden


if __name__ == "__main__":
    verify()
