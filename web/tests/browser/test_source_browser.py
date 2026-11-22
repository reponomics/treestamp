"""Source paths are selected visually without disturbing the accepted draft."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


def open_source_browser(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.locator("#submit").click()
    expect(page.locator('.source-row[data-path="."]')).to_be_visible()


@pytest.mark.parametrize("width", [390, 1280])
def test_choose_folder_and_create_without_typing(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    open_source_browser(page, service)
    tree = page.locator(".source-tree")
    root = tree.locator('[data-path="."]')
    expect(root).to_have_attribute("aria-selected", "true")
    src = tree.locator('[data-path="src"]')
    expect(src).to_have_attribute("aria-expanded", "false")
    src.locator(".source-name").click()
    expect(src).to_have_attribute("aria-selected", "true")
    expect(page.locator("#entry-selection-name")).to_have_text("src")
    page.locator("#reload").click()
    expect(page.locator("#reload-settings")).to_be_hidden()
    expect(page.locator("#rows .row")).to_have_count(3)
    expect(page.locator("#region")).to_contain_text('root = "src"')


def test_unified_keyboard_visits_files_and_expands_folders(
    page: Page, service: str
) -> None:
    open_source_browser(page, service)
    tree = page.locator(".source-tree")
    src = tree.locator('[data-path="src"]')
    src.locator(".source-name").click()
    src.press("ArrowRight")
    expect(src).to_have_attribute("aria-expanded", "true")
    file = tree.locator('[data-path="src/app.py"]')
    expect(file).to_be_visible()
    expect(file).to_have_attribute("aria-disabled", "false")
    file.click()
    expect(page.locator("#entry-selection-name")).to_have_text("src/app.py")
    src.focus()
    src.press("End")
    readme = tree.locator('[data-path="README.md"]')
    expect(readme).to_be_focused()
    scripts = tree.locator('[data-path="scripts"]')
    scripts.focus()
    scripts.press("Enter")
    src.focus()
    src.press("ArrowUp")
    scripts = tree.locator('[data-path="scripts"]')
    expect(scripts).to_be_focused()
    scripts.press("Enter")
    expect(page.locator("#entry-selection-name")).to_have_text("scripts")
    scripts.press("Home")
    expect(tree.locator('[data-path="."]')).to_be_focused()


def test_failed_document_load_preserves_selection_and_accepted_draft(
    page: Page, service: str
) -> None:
    open_source_browser(page, service)
    previous = page.locator("#region").text_content()
    address = page.url
    saved = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    page.get_by_role("button", name="Expand docs", exact=True).click()
    selected = page.locator('.source-row[data-path="docs/guide.md"]')
    selected.locator(".source-name").click()
    page.locator("#reload").click()
    expect(page.locator("#reload-error")).to_contain_text("No treestamp found")
    expect(page.locator("#entry-selection-name")).to_have_text("docs/guide.md")
    expect(selected).to_have_attribute("aria-selected", "true")
    expect(selected).to_be_focused()
    expect(page.locator('.source-row[data-path="docs"]')).to_have_attribute(
        "aria-selected", "false"
    )
    expect(page.locator("#reload")).to_have_text("Load treestamp from document")
    expect(page.locator("#region")).to_have_text(previous)
    assert page.url == address
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == saved
    page.locator("#entry-return").click()
    expect(page.locator("#region")).to_have_text(previous)


def test_directory_navigation_does_not_fetch_file_contents(
    page: Page, service: str
) -> None:
    open_source_browser(page, service)
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    docs = page.locator('.source-row[data-path="docs"]')
    docs.focus()
    docs.press("ArrowRight")
    docs.press("ArrowRight")
    api = page.locator('.source-row[data-path="docs/api.md"]')
    expect(api).to_be_focused()
    api.press("Enter")
    expect(page.locator("#entry-selection-name")).to_have_text("docs/api.md")
    assert requests == []


def test_source_browser_failure_preserves_the_existing_draft(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    previous = page.locator("#region").text_content()
    page.route(
        "**/api/browse*",
        lambda route: route.fulfill(
            status=503,
            json={"error": {"code": "upstream_unavailable", "message": "Try again"}},
        ),
    )
    page.locator("#submit").click()
    expect(page.locator("#reload-error")).to_contain_text("Try again")
    expect(page.locator("#reload")).to_be_disabled()
    expect(page.locator("#region")).to_have_text(previous)
    page.locator("#entry-return").click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#region")).to_have_text(previous)


def test_visual_selection_preserves_byte_path_identity(
    page: Page, service: str
) -> None:
    raw_path = {"git_bytes": "64ff"}
    page.route(
        "**/api/browse*",
        lambda route: route.fulfill(
            json={
                "repository": {"owner": "fixture", "name": "repo"},
                "entries": [
                    {"path": ".", "parent": None, "name": ".", "kind": "dir"},
                    {
                        "path": raw_path,
                        "parent": ".",
                        "name": raw_path,
                        "kind": "dir",
                    },
                ],
            }
        ),
    )
    open_source_browser(page, service)
    page.locator('.source-row[data-path="/git/64ff"] .source-name').click()
    page.route(
        "**/api/preview*",
        lambda route: route.fulfill(
            status=422,
            json={"error": {"code": "root_not_found", "message": "Missing fixture"}},
        ),
    )
    with page.expect_request("**/api/preview*") as request:
        page.locator("#reload").click()
    assert request.value.post_data_json["root"] == raw_path
