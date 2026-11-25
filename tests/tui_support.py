"""Shared typed fixtures and keyboard helpers for editor journeys."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from textual.widgets import Input, Static

from treestamp.editor import EditorController
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings

from .conftest import Repo

if TYPE_CHECKING:
    from textual.pilot import Pilot


@pytest.fixture(name="editor")
def editor_fixture(repo: Repo) -> EditorController:
    for path in ("src/pkg/leaf", "src/main", "readme"):
        repo.write(path)
    repo.add(".")
    return EditorController(capture_snapshot(repo.path), Settings())


def rendered_text(widget: Static) -> str:
    result = widget.render()
    plain = getattr(result, "plain", None)
    return plain if isinstance(plain, str) else str(result)


async def press(pilot: Pilot[bool], *keys: str) -> None:
    await pilot.press(*keys)
    await pilot.pause()


async def prompt(pilot: Pilot[bool], key: str) -> Input:
    await press(pilot, key)
    return pilot.app.screen.query_one("#prompt-input", Input)
