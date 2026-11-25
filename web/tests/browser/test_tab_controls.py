"""Editing Settings belong to Tree in both sidebar and popover layouts."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser

COMPACT_WIDTH = 390
WIDE_WIDTH = 1280
VIEWPORT_HEIGHT = 900


def open_settings(page: Page, *, compact: bool) -> None:
    if compact:
        page.locator(".settings-open").click()
        expect(page.locator("#settings:popover-open")).to_have_count(1)
    expect(page.locator("#settings")).to_be_visible()


@pytest.mark.parametrize("destination", ["stamp", "info"], ids=["markdown", "info"])
@pytest.mark.parametrize(
    "start_compact", [True, False], ids=["compact-to-wide", "wide-to-compact"]
)
def test_settings_remain_exclusive_to_tree_across_layout_changes(
    page: Page, service: str, destination: str, start_compact: bool
) -> None:
    page.set_viewport_size(
        {
            "width": COMPACT_WIDTH if start_compact else WIDE_WIDTH,
            "height": VIEWPORT_HEIGHT,
        }
    )
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row").first).to_be_visible()
    open_settings(page, compact=start_compact)

    page.locator(f"#tab-{destination}").click()
    expect(page.locator(f"#{destination}-panel")).to_be_visible()
    expect(page.locator("#settings:popover-open")).to_have_count(0)
    expect(page.locator("#settings")).to_be_hidden()
    expect(page.locator(".settings-open")).to_be_hidden()

    # Changing the Settings presentation must not override the active tab.
    page.set_viewport_size(
        {
            "width": WIDE_WIDTH if start_compact else COMPACT_WIDTH,
            "height": VIEWPORT_HEIGHT,
        }
    )
    expect(page.locator("#settings:popover-open")).to_have_count(0)
    expect(page.locator("#settings")).to_be_hidden()
    expect(page.locator(".settings-open")).to_be_hidden()

    page.locator("#tab-editor").click()
    expect(page.locator("#editor-panel")).to_be_visible()
    open_settings(page, compact=not start_compact)
