"""Backdrop dismissal is shared by every editor dialog on mouse and touch devices."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Browser, Page, expect  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.browser

DIALOGS = [
    ("#note-dialog", '.row[data-path="src"] [data-action="note"]'),
    ("#keymap-dialog", "#tui-help"),
    ("#repo-info-dialog", "#repo-info"),
    ("#reload-settings", "#submit"),
]


@pytest.fixture(params=[False, True], ids=["desktop-click", "mobile-tap"])
def dismissal_page(browser: Browser, request: pytest.FixtureRequest) -> Iterator[Page]:
    touch = request.param
    context = browser.new_context(
        viewport={"width": 390 if touch else 1280, "height": 844}, has_touch=touch
    )
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()


def activate_at(page: Page, x: float, y: float) -> None:
    if page.evaluate("navigator.maxTouchPoints > 0"):
        page.touchscreen.tap(x, y)
    else:
        page.mouse.click(x, y)


@pytest.mark.parametrize(("selector", "opener"), DIALOGS)
def test_backdrop_dismisses_dialog_without_applying_edits(
    dismissal_page: Page, service: str, selector: str, opener: str
) -> None:
    page = dismissal_page
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    original_region = page.locator("#region").text_content()
    origin = page.locator(opener)
    origin.click()
    dialog = page.locator(selector)
    expect(dialog).to_be_visible()
    source = {
        field: page.locator(field).input_value() for field in ("#root", "#document")
    }
    if selector == "#note-dialog":
        page.locator("#note-text").fill("discard this draft")
    elif selector == "#reload-settings":
        page.locator("#load-tab-new").click()
        page.locator("#root").fill("src")
        page.locator("#load-tab-document").click()
        page.locator("#document").fill("other.md")

    bounds = dialog.bounding_box()
    assert bounds is not None and bounds["x"] > 0 and bounds["y"] > 0
    # Bare padding targets the dialog itself, but is still inside its bounds.
    activate_at(page, bounds["x"] + 4, bounds["y"] + 4)
    expect(dialog).to_be_visible()
    activate_at(page, 1, 1)
    expect(dialog).to_be_hidden()
    expect(origin).to_be_focused()
    expect(page.locator("#region")).to_have_text(original_region)
    if selector == "#note-dialog":
        origin.click()
        expect(page.locator("#note-text")).to_have_value("")
    elif selector == "#reload-settings":
        origin.click()
        for field, value in source.items():
            expect(page.locator(field)).to_have_value(value)


@pytest.mark.parametrize(("selector", "opener"), DIALOGS)
def test_drag_from_dialog_to_backdrop_keeps_dialog_open(
    page: Page, service: str, selector: str, opener: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.locator(opener).click()
    dialog = page.locator(selector)
    bounds = dialog.bounding_box()
    assert bounds is not None
    page.mouse.move(bounds["x"] + 4, bounds["y"] + 4)
    page.mouse.down()
    page.mouse.move(1, 1)
    page.mouse.up()
    expect(dialog).to_be_visible()
    # A fresh backdrop click still dismisses after the drag.
    page.mouse.click(1, 1)
    expect(dialog).to_be_hidden()


@pytest.mark.parametrize("operation", ["note", "load"])
def test_backdrop_preserves_in_flight_dialog_operations(
    page: Page, service: str, operation: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.evaluate("""() => {
        const fetch = window.fetch.bind(window);
        window.fetch = async (...args) => {
            const response = await fetch(...args);
            await new Promise(resolve => {
                window.releaseOperation = resolve;
                document.documentElement.dataset.operationPending = "true";
            });
            return response;
        };
    }""")
    if operation == "note":
        page.locator('.row[data-path="src"] [data-action="note"]').click()
        page.locator("#note-text").fill("saved after outside click")
        page.locator("#note-save").click()
        dialog = page.locator("#note-dialog")
    else:
        page.locator("#submit").click()
        page.locator("#load-tab-new").click()
        page.locator("#reload").click()
        dialog = page.locator("#reload-settings")
    expect(page.locator("html")).to_have_attribute("data-operation-pending", "true")
    page.mouse.click(1, 1)
    expect(dialog).to_be_visible()
    page.evaluate("window.releaseOperation()")
    expect(dialog).to_be_hidden()
    if operation == "note":
        expect(page.locator('.row[data-path="src"] .note')).to_have_text(
            "# saved after outside click"
        )
    else:
        expect(page.locator("#tree-document")).to_have_text("")
