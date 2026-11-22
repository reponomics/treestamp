"""Startup choices remain clear and usable with keyboard or mouse focus."""

from __future__ import annotations

import asyncio

import pytest
from textual.app import App


@pytest.mark.parametrize("text", ["", "first\nsecond\nthird\n"])
def test_preview_home_end_navigate_readonly_text(text: str) -> None:
    from textual.widgets import TextArea

    from treestamp.tui_dialogs import PreviewScreen

    class PreviewApp(App[None]):
        def on_mount(self) -> None:
            self.push_screen(PreviewScreen("Preview", text))

    async def journey() -> None:
        app = PreviewApp()
        async with app.run_test() as pilot:
            area = app.screen.query_one(TextArea)
            assert area.read_only
            await pilot.press("end")
            lines = text.splitlines() or [""]
            assert area.cursor_location == (len(lines) - 1, len(lines[-1]))
            await pilot.press("home")
            assert area.cursor_location == (0, 0)
            assert area.text == text
            await pilot.press("escape")
            assert len(app.screen_stack) == 1

    asyncio.run(journey())
