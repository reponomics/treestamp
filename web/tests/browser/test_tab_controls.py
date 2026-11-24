"""Each view exposes its own controls without changing the accepted treestamp."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = [
    pytest.mark.browser,
    pytest.mark.parametrize("width", [390, 768, 1280]),
]


def open_editor(page: Page, service: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row").first).to_be_visible()
    expect(page.locator("#submit")).to_be_enabled()


def open_settings(page: Page, width: int) -> None:
    if width < 1024:
        page.locator(".settings-open").click()
        expect(page.locator("#settings:popover-open")).to_have_count(1)
    expect(page.locator("#settings")).to_be_visible()


@pytest.mark.parametrize("destination", ["stamp", "info"])
def test_editing_settings_follow_tree_view_through_navigation_and_resize(
    page: Page, service: str, width: int, destination: str
) -> None:
    open_editor(page, service, width)
    open_settings(page, width)
    page.locator("#attribution").check()
    expect(page.locator("#tree-attribution")).to_be_visible()
    original_output = page.locator("#region").text_content()
    original_url = page.url
    original_draft = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if "/api/" in request.url else None
        ),
    )

    page.locator(f"#tab-{destination}").click()
    expect(page.locator(f"#{destination}-panel")).to_be_visible()
    expect(page.locator("#settings:popover-open")).to_have_count(0)
    expect(page.locator("#settings")).to_be_hidden()
    expect(page.locator(".settings-open")).to_be_hidden()

    # A change from popover to sidebar (or back) must not expose editing controls.
    resized_width = 1280 if width < 1024 else 390
    page.set_viewport_size({"width": resized_width, "height": 900})
    expect(page.locator("#settings")).to_be_hidden()
    expect(page.locator(".settings-open")).to_be_hidden()
    page.locator(f"#tab-{destination}").press("Home")
    expect(page.locator("#tab-editor")).to_be_focused()
    expect(page.locator("#editor-panel")).to_be_visible()
    open_settings(page, resized_width)
    expect(page.locator("#attribution")).to_be_checked()
    expect(page.locator("#region")).to_have_text(original_output)
    assert page.url == original_url
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == (
        original_draft
    )
    assert requests == []


def test_markdown_keeps_format_and_copy_available_without_editing_settings(
    page: Page, service: str, width: int
) -> None:
    open_editor(page, service, width)
    original_output = page.locator("#region").text_content()
    page.locator("#tab-editor").press("ArrowRight")
    expect(page.locator("#tab-stamp")).to_be_focused()
    expect(page.locator("#settings")).to_be_hidden()
    expect(page.locator(".settings-open")).to_be_hidden()
    expect(page.locator("#style")).to_be_visible()
    expect(page.locator("#copy")).to_be_visible()
    expect(page.locator("#copy")).to_be_enabled()

    with page.expect_response("**/api/op") as operation:
        page.locator("#style").select_option("ascii")
    accepted = operation.value.json()
    expect(page.locator("#region")).to_have_text(accepted["region"])
    assert accepted["region"] != original_output
    assert accepted["state"]["curation"]["settings"]["style"] == "ascii"
    expect(page.locator("#settings")).to_be_hidden()
    expect(page.locator("#copy")).to_be_enabled()

    page.locator("#tab-editor").click()
    open_settings(page, width)
    page.locator("#tab-stamp").click()
    expect(page.locator("#style")).to_have_value("ascii")
    expect(page.locator("#region")).to_have_text(accepted["region"])
    expect(page.locator("#settings:popover-open")).to_have_count(0)
