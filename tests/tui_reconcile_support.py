"""Typed fixtures and helpers for queued note-transfer journeys."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.widgets import Static

from treestamp.document import write_document
from treestamp.editor import EditorController
from treestamp.gitio import capture_snapshot
from treestamp.model import Node, Settings
from treestamp.tui_reconcile import (
    PlacementChoiceScreen,
    ReconcileScreen,
)

from .conftest import Repo

if TYPE_CHECKING:
    from textual.pilot import Pilot

NOTES = {"old/a.py": "First annotation", "old/b.py": "Second annotation"}


def load_stale(repo: Repo) -> EditorController:
    """Move two annotated rows into a previously collapsed existing directory."""
    for path in ("old/a.py", "old/b.py", "pkg/existing.py"):
        repo.write(path)
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())
    session = editor.state.session
    session.expand("old")
    for path, note in NOTES.items():
        session.set_annotation(path, note)
    write_document(editor.document(), repo.path / "tree.md", create=True)
    repo.git("mv", "old/a.py", "pkg/first.py")
    repo.git("mv", "old/b.py", "pkg/second.py")
    editor.adopt(editor.prepare_load("tree.md"))
    return editor


@pytest.fixture(name="stale")
def stale_fixture(repo: Repo) -> EditorController:
    return load_stale(repo)


def text_of(widget: Static) -> str:
    rendered = widget.render()
    plain = getattr(rendered, "plain", None)
    return plain if isinstance(plain, str) else str(rendered)


async def press(pilot: Pilot[bool], *keys: str) -> None:
    await pilot.press(*keys)
    await pilot.pause()


async def opened(pilot: Pilot[bool], *, skip_group: bool = True) -> ReconcileScreen:
    assert isinstance(pilot.app.screen, PlacementChoiceScreen)
    await press(pilot, "enter")
    screen = pilot.app.screen
    assert isinstance(screen, ReconcileScreen)
    current = screen.state.current
    assert current is not None
    if skip_group and current.is_dir and not current.annotation:
        await press(pilot, "s")
    return screen


def selected(screen: ReconcileScreen) -> str:
    assert screen.tree_view.index is not None
    return screen.rows[screen.tree_view.index][0].path


def current(screen: ReconcileScreen) -> Node:
    source = screen.state.current
    assert source is not None
    return source
