"""Startup choices remain clear and usable with keyboard or mouse focus."""

from __future__ import annotations

import asyncio

import pytest
from textual.app import App
from textual.widgets import Button, Static

from treestamp.tui_dialogs import DocumentChoiceScreen


class ChoiceApp(App[str | None]):
    def on_mount(self) -> None:
        self.push_screen(DocumentChoiceScreen(), self.exit)


def description(app: ChoiceApp) -> str:
    return str(app.screen.query_one("#choice-description", Static).render())


@pytest.mark.parametrize(
    ("keys", "expected"),
    [((), "new"), (("down",), "load"), (("down", "up"), "new"), (("up",), "load")],
)
def test_arrows_select_startup_choice(keys: tuple[str, ...], expected: str) -> None:
    async def journey() -> None:
        app = ChoiceApp()
        async with app.run_test() as pilot:
            assert app.focused is app.screen.query_one("#new", Button)
            assert "Start a tree" in description(app)
            await pilot.press(*keys)
            await pilot.pause()
            assert app.focused is app.screen.query_one(f"#{expected}", Button)
            assert (
                "Start a tree" if expected == "new" else "Open a document"
            ) in description(app)
            await pilot.press("enter")
        assert app.return_value == expected

    asyncio.run(journey())


def test_tab_and_mouse_focus_update_startup_description() -> None:
    async def journey() -> None:
        app = ChoiceApp()
        async with app.run_test() as pilot:
            await pilot.press("tab")
            await pilot.pause()
            assert app.focused is app.screen.query_one("#load", Button)
            assert "Open a document" in description(app)
            await pilot.press("shift+tab")
            await pilot.pause()
            assert "Start a tree" in description(app)
            await pilot.mouse_down("#load")
            await pilot.pause()
            assert "Open a document" in description(app)
            await pilot.mouse_up("#load")
            await pilot.press("enter")
        assert app.return_value == "load"

    asyncio.run(journey())


@pytest.mark.parametrize("size", [(80, 24), (40, 20)])
def test_startup_panel_fits_compact_terminal(size: tuple[int, int]) -> None:
    async def journey() -> None:
        app = ChoiceApp()
        async with app.run_test(size=size) as pilot:
            for selector in ("#new", "#load", "#choice-description", "#choice-help"):
                widget = app.screen.query_one(selector)
                assert widget.region in app.screen.region
            await pilot.press("down")
            await pilot.pause()
            assert app.screen.query_one("#choice-help").region in app.screen.region

    asyncio.run(journey())
