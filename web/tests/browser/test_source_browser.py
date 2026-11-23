"""Source paths are selected visually without disturbing the accepted draft."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Browser, Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


def open_source_browser(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.locator("#browse-source").click()
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
    expect(src).to_have_attribute("aria-expanded", "true")
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
    src.focus()
    src.press("ArrowRight")
    expect(src).to_have_attribute("aria-expanded", "true")
    file = tree.locator('[data-path="src/app.py"]')
    expect(file).to_be_visible()
    expect(file).to_have_attribute("aria-disabled", "false")
    file.click()
    expect(page.locator('.source-row[data-path="src/app.py"]')).to_have_attribute(
        "aria-selected", "true"
    )
    src.focus()
    src.press("End")
    readme = tree.locator('[data-path="README.md"]')
    expect(readme).to_be_focused()
    scripts = tree.locator('[data-path="scripts"]')
    scripts.focus()
    scripts.press("Enter")
    expect(scripts).to_have_attribute("aria-expanded", "true")
    scripts.press("ArrowLeft")
    expect(scripts).to_have_attribute("aria-expanded", "false")
    src.focus()
    src.press("ArrowUp")
    scripts = tree.locator('[data-path="scripts"]')
    expect(scripts).to_be_focused()
    scripts.press("Space")
    expect(scripts).to_have_attribute("aria-expanded", "true")
    expect(page.locator('.source-row[data-path="scripts"]')).to_have_attribute(
        "aria-selected", "true"
    )
    scripts.press("Home")
    expect(tree.locator('[data-path="."]')).to_be_focused()


def test_failed_document_load_preserves_selection_and_accepted_draft(
    page: Page, service: str
) -> None:
    open_source_browser(page, service)
    previous = page.locator("#region").text_content()
    address = page.url
    saved = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    page.locator('.source-row[data-path="docs"]').click()
    selected = page.locator('.source-row[data-path="docs/guide.md"]')
    selected.locator(".source-name").click()
    page.locator("#reload").click()
    expect(page.locator("#reload-error")).to_contain_text("No treestamp found")
    expect(selected).to_have_attribute("aria-selected", "true")
    expect(selected).to_be_focused()
    expect(page.locator('.source-row[data-path="docs"]')).to_have_attribute(
        "aria-selected", "false"
    )
    expect(page.locator("#reload")).to_have_text("Load")
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
    expect(page.locator('.source-row[data-path="docs/api.md"]')).to_have_attribute(
        "aria-selected", "true"
    )
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
    page.locator("#browse-source").click()
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


@pytest.mark.parametrize(
    ("width", "touch"), [(390, False), (390, True), (768, False), (1280, False)]
)
def test_picker_matches_editor_tree_density_and_indentation(
    browser: Browser, service: str, width: int, touch: bool
) -> None:
    with browser.new_context(
        viewport={"width": width, "height": 844}, has_touch=touch
    ) as context:
        page = context.new_page()
        page.goto(f"{service}/fixture/repo?root=.")
        expect(page.locator("#rows .row")).to_have_count(9)
        page.evaluate("document.fonts.ready")
        editor_root = page.locator('.row[data-path=""]')
        editor_folder = page.locator('.row[data-path="src"]')
        geometry = """(row, labelSelector) => {
            const label = row.querySelector(labelSelector);
            const style = getComputedStyle(label);
            return {
                height: row.getBoundingClientRect().height,
                labelOffset: label.getBoundingClientRect().x - row.getBoundingClientRect().x,
                font: style.fontFamily,
                size: style.fontSize,
            };
        }"""
        root_before = editor_root.evaluate(geometry, ".name")
        folder_before = editor_folder.evaluate(geometry, ".name")
        page.locator("#browse-source").click()
        source_root = page.locator('.source-row[data-path="."]')
        source_folder = page.locator('.source-row[data-path="src"]')
        expect(source_folder).to_be_visible()
        root_after = source_root.evaluate(geometry, ".source-name")
        folder_after = source_folder.evaluate(geometry, ".source-name")
        for before, after in ((root_before, root_after), (folder_before, folder_after)):
            assert after["height"] == pytest.approx(before["height"], abs=0.5)
            assert after["height"] == pytest.approx(32, abs=0.5)
            assert after["labelOffset"] == pytest.approx(before["labelOffset"], abs=0.5)
            assert after["font"] == before["font"]
            assert after["size"] == before["size"] == "16px"
        file = page.locator('.source-row[data-path="README.md"]')
        expect(file.locator(".source-toggle")).to_have_count(0)
        expect(file).to_have_text("README.md")
        expect(
            page.locator(".source-tree .source-toggle, .source-tree button")
        ).to_have_count(0)


def test_picker_row_activation_selects_toggles_and_keeps_branch_continuity(
    page: Page, service: str
) -> None:
    open_source_browser(page, service)
    tree = page.locator(".source-tree")
    root = tree.locator('[data-path="."]')
    docs = tree.locator('[data-path="docs"]')
    page.locator('.source-row[data-path="docs"]').click()
    expect(root).to_have_attribute("aria-selected", "false")
    expect(docs).to_have_attribute("aria-selected", "true")
    expect(docs).to_have_attribute("aria-expanded", "true")
    first_file = tree.locator('[data-path="docs/api.md"]')
    last_file = tree.locator('[data-path="docs/guide.md"]')
    expect(first_file.locator(".indent")).to_have_count(2)
    expect(first_file.locator(".indent.trunk")).to_have_count(1)
    expect(first_file.locator(".indent.branch:not(.last)")).to_have_count(1)
    expect(last_file.locator(".indent.trunk")).to_have_count(1)
    expect(last_file.locator(".indent.branch.last")).to_have_count(1)
    expect(tree.locator('[data-path="README.md"] .indent.branch.last')).to_have_count(1)
    expect(tree.locator('[data-path="."] .indent')).to_have_count(0)
    last_file.locator(".source-name").click()
    expect(last_file).to_have_attribute("aria-selected", "true")
    page.locator('.source-row[data-path="docs"]').click()
    expect(last_file).to_have_count(0)
    expect(docs).to_have_attribute("aria-selected", "true")
    expect(docs).to_have_attribute("aria-expanded", "false")
    page.locator('.source-row[data-path="docs"]').click()
    expect(docs).to_have_attribute("aria-selected", "true")
    expect(docs).to_have_attribute("aria-expanded", "true")
    expect(last_file).to_have_attribute("aria-selected", "false")
    expect(last_file.locator(".indent.branch.last")).to_have_count(1)
