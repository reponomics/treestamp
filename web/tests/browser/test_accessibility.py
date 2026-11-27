"""Existing controls expose useful semantics and preserve keyboard focus."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


def open_editor(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")


def test_accessibility_fold_spacers_are_not_exposed_as_buttons(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    expect(page.get_by_role("button", name="", exact=True)).to_have_count(0)
    root = page.locator('.row[data-path=""]')
    expect(root.get_by_role("button")).to_have_count(0)
    expect(page.get_by_role("button", name="Note", exact=True)).to_be_enabled()
    expect(page.get_by_role("button", name="Hide", exact=True)).to_be_disabled()
    expect(
        page.locator('.row[data-path="docs/api.md"]').get_by_role("button")
    ).to_have_count(0)
    fold = page.get_by_role("button", name="Close docs", exact=True)
    expect(fold).to_have_attribute("aria-expanded", "true")
    fold.press("Enter")
    expect(page.get_by_role("button", name="Open docs", exact=True)).to_be_focused()


def test_accessibility_view_tabs_leave_modified_keys_to_the_browser(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    tab = page.get_by_role("tab", name="Tree", exact=True)
    tab.focus()
    for modifier in ["altKey", "ctrlKey", "metaKey", "shiftKey"]:
        allowed = tab.evaluate(
            """(element, modifier) => element.dispatchEvent(new KeyboardEvent(
                "keydown", {key: "ArrowRight", [modifier]: true, bubbles: true, cancelable: true}
            ))""",
            modifier,
        )
        assert allowed, f"The tab handler cancelled {modifier}+ArrowRight"
        expect(tab).to_have_attribute("aria-selected", "true")
        expect(tab).to_be_focused()
    tab.press("ArrowRight")
    expect(page.get_by_role("tab", name="Export", exact=True)).to_be_focused()


def test_hiding_last_child_selects_root_and_focuses_enabled_note_action(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    for path in ["docs", "scripts", "src"]:
        row = page.locator(f'.row[data-path="{path}"]')
        row.focus()
        page.locator("#row-visibility").click()
        expect(row).to_have_count(0)
    root = page.locator('.row[data-path=""]')
    expect(root).to_have_attribute("data-selected", "true")
    expect(page.locator("#row-note")).to_be_focused()
    expect(page.get_by_role("button", name="Hide", exact=True)).to_be_disabled()
