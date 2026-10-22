"""Tree keyboard navigation follows the TUI and respects pending editing work."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Locator, Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


def row(page: Page, path: str) -> Locator:
    return page.locator(f'#rows .row[data-path="{path}"]')


def open_editor(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#submit")).to_be_enabled()
    page.locator("#tui-mode").click()
    expect(page.locator("#tui-mode")).to_have_attribute("aria-pressed", "true")


def delay_next_operation(page: Page) -> None:
    page.evaluate("""() => {
        const originalFetch = window.fetch.bind(window);
        let delayed = false;
        window.fetch = async (...args) => {
            const response = await originalFetch(...args);
            if (args[0] === "/api/op" && !delayed) {
                delayed = true;
                await new Promise(resolve => {
                    window.releaseNavigation = resolve;
                    document.documentElement.dataset.navigationPending = "true";
                });
            }
            return response;
        };
    }""")


def test_navigation_browses_rows_and_expands_before_entering_children(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    root = row(page, "")
    root.focus()
    for key in ["ArrowUp", "ArrowLeft", "Space"]:
        page.keyboard.press(key)
        expect(root).to_be_focused()
        expect(page.locator("#rows .row")).to_have_count(9)

    for key, path in [
        ("ArrowRight", "docs"),
        ("ArrowRight", "docs/api.md"),
        ("ArrowRight", "docs/api.md"),
        ("ArrowDown", "docs/guide.md"),
        ("ArrowUp", "docs/api.md"),
        ("ArrowLeft", "docs"),
        ("ArrowLeft", "docs"),
    ]:
        page.keyboard.press(key)
        expect(row(page, path)).to_be_focused()
    expect(row(page, "docs/api.md")).to_have_count(0)
    page.keyboard.press("ArrowRight")
    expect(row(page, "docs/api.md")).to_have_count(1)
    expect(row(page, "docs")).to_be_focused()
    page.keyboard.press("ArrowRight")
    expect(row(page, "docs/api.md")).to_be_focused()
    page.keyboard.press("End")
    expect(row(page, "src/util.py")).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(row(page, "src/util.py")).to_be_focused()
    page.keyboard.press("Home")
    expect(root).to_be_focused()

    row(page, "docs").locator(".fold").focus()
    page.keyboard.press("ArrowDown")
    expect(row(page, "docs/api.md")).to_be_focused()


def test_navigation_leaves_note_carets_and_native_button_space_intact(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    docs = row(page, "docs")
    docs.locator(".fold").focus()
    page.keyboard.press("Space")
    expect(row(page, "docs/api.md")).to_have_count(0)
    expect(docs.locator(".fold")).to_be_focused()
    docs.focus()
    page.keyboard.press("Space")
    expect(row(page, "docs/api.md")).to_have_count(1)
    expect(docs).to_be_focused()

    docs.locator('[data-action="note"]').focus()
    page.keyboard.press("Space")
    note = page.locator("#note-text")
    expect(note).to_be_focused()
    note.fill("abc")
    note.press("ArrowLeft")
    note.press("X")
    expect(note).to_have_value("abXc")
    for key in ["ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"]:
        note.press(key)
        expect(note).to_be_focused()
    note.press("Escape")
    expect(docs.locator('[data-action="note"]')).to_be_focused()
    expect(row(page, "docs/api.md")).to_have_count(1)
    docs.focus()
    for key in [
        "Alt+ArrowLeft",
        "Control+ArrowRight",
        "Meta+ArrowDown",
        "Shift+ArrowUp",
    ]:
        page.keyboard.press(key)
        expect(docs).to_be_focused()
    expect(row(page, "docs/api.md")).to_have_count(1)


def test_navigation_handles_excluded_children_without_jumping_to_a_sibling(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    for path in ["docs/api.md", "docs/guide.md"]:
        child = row(page, path)
        child.locator('[data-action="visibility"]').click()
        expect(child).to_have_count(0)
    docs = row(page, "docs")
    docs.focus()
    page.keyboard.press("ArrowRight")
    expect(docs).to_be_focused()
    # Visually closed because every child is excluded, but actually still expanded.
    with page.expect_request("**/api/op") as operation:
        page.keyboard.press("ArrowLeft")
    assert operation.value.post_data_json["op"]["type"] == "collapse"
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")
    expect(docs).to_be_focused()
    page.keyboard.press("ArrowLeft")
    expect(row(page, "")).to_be_focused()

    page.locator("#reveal").check()
    expect(docs).to_have_count(1)
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")
    docs.focus()
    page.keyboard.press("ArrowRight")
    expect(row(page, "docs/api.md")).to_have_class("row leaf hidden-row")
    page.keyboard.press("ArrowRight")
    expect(row(page, "docs/api.md")).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(row(page, "docs/guide.md")).to_be_focused()
    page.keyboard.press("ArrowLeft")
    expect(docs).to_be_focused()


@pytest.mark.parametrize(
    "keys", [("ArrowRight", "ArrowRight"), ("ArrowLeft", "ArrowRight")]
)
def test_navigation_serializes_rapid_keys_against_the_updated_rows(
    page: Page, service: str, keys: tuple[str, str]
) -> None:
    open_editor(page, service)
    docs = row(page, "docs")
    if keys[0] == "ArrowRight":
        docs.locator(".fold").click()
        expect(row(page, "docs/api.md")).to_have_count(0)
    delay_next_operation(page)
    docs.focus()
    page.keyboard.press(keys[0])
    expect(page.locator("html")).to_have_attribute("data-navigation-pending", "true")
    page.keyboard.press(keys[1])
    page.evaluate("window.releaseNavigation()")
    expect(row(page, "docs/api.md")).to_have_count(1)
    expected = "docs/api.md" if keys[0] == "ArrowRight" else "docs"
    expect(row(page, expected)).to_be_focused()
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")


def test_navigation_does_not_steal_focus_back_from_info(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    delay_next_operation(page)
    row(page, "docs").focus()
    page.keyboard.press("ArrowLeft")
    expect(page.locator("html")).to_have_attribute("data-navigation-pending", "true")
    page.keyboard.press("ArrowRight")
    info = page.get_by_role("tab", name="Info", exact=True)
    info.click()
    page.evaluate("window.releaseNavigation()")
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")
    expect(info).to_be_focused()
    expect(page.locator("#info-panel")).to_be_visible()
    expect(row(page, "docs/api.md")).to_have_count(0)
    page.get_by_role("tab", name="Tree", exact=True).click()
    expect(row(page, "docs/api.md")).to_have_count(0)


def test_navigation_after_a_failed_edit_keeps_previous_draft_copyable(
    page: Page, service: str
) -> None:
    page.add_init_script("""
        window.copiedBlocks = [];
        Object.defineProperty(navigator, "clipboard", {value: {
            writeText: async text => window.copiedBlocks.push(text)
        }});
    """)
    open_editor(page, service)
    page.route(
        "**/api/op",
        lambda route: route.fulfill(
            status=503, json={"error": {"message": "Could not save the edit."}}
        ),
    )
    docs = row(page, "docs")
    docs.locator(".fold").click()
    expect(page.locator("#error")).to_contain_text("Could not save the edit.")
    docs.focus()
    page.keyboard.press("ArrowDown")
    expect(row(page, "docs/api.md")).to_be_focused()
    page.locator("#copy").click()
    expect(page.locator("#copy-status")).to_have_text("Copied previous draft")
    expect(page.locator("#copy-label")).to_have_text("Copied")
    assert page.evaluate("window.copiedBlocks") == [
        page.locator("#region").text_content()
    ]


def test_navigation_pages_and_keeps_the_focused_row_inside_a_short_pane(
    page: Page, service: str
) -> None:
    page.set_viewport_size({"width": 1280, "height": 420})
    open_editor(page, service)
    root = row(page, "")
    root.focus()
    page.keyboard.press("PageDown")
    expect(root).not_to_be_focused()
    expect(row(page, "src/util.py")).not_to_be_focused()
    page.keyboard.press("PageUp")
    expect(root).to_be_focused()
    for key, path in [("End", "src/util.py"), ("Home", "")]:
        page.keyboard.press(key)
        focused = row(page, path)
        expect(focused).to_be_focused()
        expect(focused).to_be_in_viewport(ratio=1)
        tree_bounds = page.locator(".tree-scroll").bounding_box()
        row_bounds = focused.bounding_box()
        assert tree_bounds is not None and row_bounds is not None
        assert tree_bounds["y"] <= row_bounds["y"]
        assert (
            row_bounds["y"] + row_bounds["height"]
            <= tree_bounds["y"] + tree_bounds["height"]
        )
    assert page.evaluate("document.documentElement.scrollHeight <= window.innerHeight")
