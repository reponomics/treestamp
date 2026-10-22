"""Existing controls expose useful semantics and preserve keyboard focus."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, Route, expect  # noqa: E402

pytestmark = pytest.mark.browser


def open_editor(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#submit")).to_be_enabled()


def test_accessibility_fold_spacers_are_not_exposed_as_buttons(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    expect(page.get_by_role("button", name="", exact=True)).to_have_count(0)
    root = page.locator('.row[data-path=""]')
    expect(root.get_by_role("button")).to_have_count(2)
    expect(root.get_by_role("button", name="Note", exact=True)).to_be_enabled()
    expect(root.get_by_role("button", name="Hide", exact=True)).to_be_disabled()
    expect(
        page.locator('.row[data-path="docs/api.md"]').get_by_role("button")
    ).to_have_count(2)
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
    expect(page.get_by_role("tab", name="Markdown", exact=True)).to_be_focused()


def test_hiding_last_child_returns_focus_to_root_instead_of_disabled_hide(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    for path in ["docs", "scripts", "src"]:
        row = page.locator(f'.row[data-path="{path}"]')
        row.get_by_role("button", name="Hide", exact=True).click()
        expect(row).to_have_count(0)
    root = page.locator('.row[data-path=""]')
    expect(root).to_be_focused()
    expect(root.get_by_role("button", name="Hide", exact=True)).to_be_disabled()


def test_accessibility_keyboard_undo_returns_to_the_restored_row(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    docs = page.locator('.row[data-path="docs"]')
    docs.get_by_role("button", name="Hide", exact=True).click()
    expect(docs).to_have_count(0)
    undo = page.get_by_role("button", name="Undo", exact=True)
    undo.focus()
    undo.press("Enter")
    expect(docs).to_have_count(1)
    expect(docs).to_be_focused()
    expect(page.locator("#notice")).to_be_hidden()


def test_accessibility_failed_undo_keeps_the_action_available_for_retry(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    docs = page.locator('.row[data-path="docs"]')
    docs.get_by_role("button", name="Hide", exact=True).click()
    expect(docs).to_have_count(0)
    page.route(
        "**/api/op",
        lambda route: route.fulfill(
            status=503, json={"error": {"message": "Could not restore the entry."}}
        ),
    )
    undo = page.get_by_role("button", name="Undo", exact=True)
    undo.focus()
    undo.press("Enter")
    expect(page.locator("#error")).to_contain_text("Could not restore the entry.")
    expect(undo).to_be_visible()
    expect(undo).to_be_enabled()
    expect(undo).to_be_focused()
    expect(docs).to_have_count(0)
    page.unroute("**/api/op")
    undo.press("Enter")
    expect(docs).to_be_focused()
    expect(page.locator("#notice")).to_be_hidden()


def test_accessibility_pending_undo_respects_focus_moved_to_info(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    docs = page.locator('.row[data-path="docs"]')
    docs.get_by_role("button", name="Hide", exact=True).click()
    expect(docs).to_have_count(0)
    pending: list[Route] = []
    page.route("**/api/op", lambda route: pending.append(route))
    undo = page.get_by_role("button", name="Undo", exact=True)
    undo.focus()
    undo.press("Enter")
    expect(undo).to_have_attribute("aria-disabled", "true")
    info = page.get_by_role("tab", name="Info", exact=True)
    info.click()
    assert len(pending) == 1
    pending[0].continue_()
    expect(docs).to_have_count(1)
    expect(info).to_be_focused()
    expect(page.locator("#info-panel")).to_be_visible()
