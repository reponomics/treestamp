"""Pointer targets and scroll stability while editing a tree."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


@pytest.fixture
def browser_context_args(browser_context_args: dict) -> dict:
    return {**browser_context_args, "has_touch": True}


def test_mobile_fold_keeps_page_position(page: Page, service: str) -> None:
    page.set_viewport_size({"width": 390, "height": 500})
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.evaluate("document.fonts.ready")
    docs = page.locator('.row[data-path="docs"]')
    docs.evaluate(
        "node => window.scrollTo(0, node.getBoundingClientRect().top + window.scrollY - 80)"
    )
    before = page.evaluate("window.scrollY")
    assert before > 200
    docs.locator(".fold").click()
    expect(page.locator('.row[data-path="docs/api.md"]')).to_have_count(0)
    expected = page.evaluate(
        "before => Math.min(before, document.documentElement.scrollHeight - innerHeight)",
        before,
    )
    assert page.evaluate("window.scrollY") == pytest.approx(expected, abs=2)
    docs.locator(".fold").click()
    expect(page.locator('.row[data-path="docs/api.md"]')).to_have_count(1)
    assert page.evaluate("window.scrollY") == pytest.approx(expected, abs=2)


@pytest.mark.parametrize(("width", "gesture"), [(390, "tap"), (1280, "click")])
def test_directory_row_padding_toggles_once_without_affecting_actions(
    page: Page, service: str, width: int, gesture: str
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    docs = page.locator('.row[data-path="docs"]')
    getattr(docs, gesture)(position={"x": 5, "y": 12})
    expect(docs.locator(".fold")).to_have_attribute("aria-expanded", "false")
    expect(docs).to_be_focused()
    docs.locator(".counts").click()
    expect(docs.locator(".fold")).to_have_attribute("aria-expanded", "true")
    docs.locator('[data-action="note"]').click()
    expect(page.locator("#note-text")).to_be_focused()
    expect(docs.locator(".fold")).to_have_attribute("aria-expanded", "true")
    page.locator("#note-text").press("Escape")
    docs.locator(".name").click()
    expect(docs.locator(".fold")).to_have_attribute("aria-expanded", "false")
    docs.locator(".fold").click()
    expect(docs.locator(".fold")).to_have_attribute("aria-expanded", "true")


def test_pending_fold_respects_scrolling_before_response(
    page: Page, service: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 500})
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.evaluate("document.fonts.ready")
    page.evaluate("""() => {
        const fetch = window.fetch.bind(window);
        window.fetch = async (...args) => {
            const response = await fetch(...args);
            if (args[0] === '/api/op') {
                await new Promise(resolve => {
                    window.releaseFold = resolve;
                    document.documentElement.dataset.foldPending = 'true';
                });
            }
            return response;
        };
    }""")
    page.locator('.row[data-path="docs"] .fold').click()
    expect(page.locator("html")).to_have_attribute("data-fold-pending", "true")
    page.evaluate("window.scrollTo(0, 150)")
    expect(page.locator("#url")).not_to_be_focused()
    page.evaluate("window.releaseFold()")
    expect(page.locator('.row[data-path="docs/api.md"]')).to_have_count(0)
    assert page.evaluate("window.scrollY") == pytest.approx(150, abs=2)


def test_fold_keeps_desktop_tree_scroll_position(page: Page, service: str) -> None:
    page.set_viewport_size({"width": 1280, "height": 420})
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    src = page.locator('.row[data-path="src"]')
    src.scroll_into_view_if_needed()
    tree = page.locator(".tree-scroll")
    before = tree.evaluate("node => node.scrollTop")
    assert before > 0
    src.locator(".fold").click()
    expect(page.locator('.row[data-path="src/app.py"]')).to_have_count(0)
    expected = tree.evaluate(
        "(node, before) => Math.min(before, node.scrollHeight - node.clientHeight)",
        before,
    )
    assert tree.evaluate("node => node.scrollTop") == pytest.approx(expected, abs=2)
