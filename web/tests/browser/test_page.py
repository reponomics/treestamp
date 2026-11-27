"""The page's journeys against the fixture repository, one test per state."""

from __future__ import annotations

import re

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser

REPOSITORY = "fixture/repo"  # the fake maps every name to the fixture checkout


def submit(page: Page, service: str, url: str = REPOSITORY) -> None:
    page.goto(service + "/")
    page.fill("#entry-url", url)
    page.click("#entry-browse")
    page.locator('.source-row[data-path="README.md"]').click()
    page.click("#source-load")
    expect(page.locator("#reload-settings")).to_be_hidden()
    page.wait_for_selector("#rows .row")
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")


def test_first_load_shows_the_loaded_treestamp_without_script_errors(
    page: Page, service: str
) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    submit(page, service)
    expect(page.locator("#source-origin")).to_have_count(0)
    page.locator(".wordmark").click()
    page.locator("#entry-url").fill("fixture/repo")
    page.locator("#entry-browse").click()
    expect(page.locator("#source-origin")).to_have_count(0)
    expect(page.locator("#rows .row")).to_have_count(9)  # . + 3 dirs + 5 files
    expect(page.locator('#rows .row[data-path="docs"] .name')).to_have_text("docs/")
    assert errors == []


@pytest.mark.parametrize("width", [320, 390, 820, 1280])
def test_repository_info_tooltip_does_not_move_the_layout(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    submit(page, service)
    link = page.get_by_role("link", name="Visit repo", exact=True)
    expect(link).to_be_visible()
    expect(link).to_have_attribute("href", "https://github.com/fixture/repo")
    expect(link).to_have_attribute("target", "_blank")
    expect(link).to_have_attribute("rel", "noopener")
    expect(link.locator("svg")).to_be_visible()
    expect(link).to_have_css("text-decoration-line", "none")
    expect(
        page.locator("#repo-details, #repo-details-open, #entries, #meta, #reload-open")
    ).to_have_count(0)
    info = page.get_by_role("button", name="Repository information", exact=True)
    tooltip = page.locator("#repo-tooltip")
    expect(tooltip).to_be_hidden()
    before = page.locator("#active-repository, #rows").evaluate_all(
        "elements => elements.map(element => element.getBoundingClientRect().toJSON())"
    )
    info.hover()
    expect(tooltip).to_be_visible()
    expect(tooltip).to_contain_text("Branch: main")
    expect(tooltip.locator("[data-repo-commit]")).to_have_text(
        re.compile(r"[a-f0-9]{40}")
    )
    expect(tooltip).to_be_in_viewport(ratio=1)
    assert tooltip.evaluate("node => node.scrollWidth <= node.clientWidth")
    # Containment alone misses clipping by a scrolling sidebar. Probe each
    # corner inside the border to ensure the full tooltip is actually exposed.
    assert tooltip.evaluate("""node => {
        const box = node.getBoundingClientRect();
        return [box.left + 2, box.right - 2].every(x =>
            [box.top + 2, box.bottom - 2].every(y =>
                node.contains(document.elementFromPoint(x, y))));
    }""")
    assert (
        page.locator("#active-repository, #rows").evaluate_all(
            "elements => elements.map(element => element.getBoundingClientRect().toJSON())"
        )
        == before
    )
    info.press("Escape")
    expect(tooltip).to_be_hidden()
    # A keyboard user can discover the same tooltip by focusing its trigger.
    page.locator("#visit-repo").focus()
    info.focus()
    expect(tooltip).to_be_visible()
    info.press("Escape")
    expect(tooltip).to_be_hidden()


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("close", ["button", "Escape"])
def test_repository_information_modal_returns_focus(
    page: Page, service: str, width: int, close: str
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    submit(page, service)
    info = page.get_by_role("button", name="Repository information", exact=True)
    info.click()
    dialog = page.locator("#repo-info-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("[data-repo-branch]")).to_have_text("main")
    expect(dialog.locator("[data-repo-commit]")).to_have_text(
        re.compile(r"[a-f0-9]{40}")
    )
    assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth")
    bounds = dialog.bounding_box()
    assert (
        bounds is not None
        and bounds["x"] >= 0
        and bounds["x"] + bounds["width"] <= width
    )
    if close == "button":
        dialog.get_by_role("button", name="Close", exact=True).click()
    else:
        page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(info).to_be_focused()
    tooltip = page.locator("#repo-tooltip")
    expect(tooltip).to_be_hidden()
    # Restored pointer focus must not pin a later hover tooltip open.
    page.mouse.move(0, 0)
    info.hover()
    expect(tooltip).to_be_visible()
    tooltip.hover()
    expect(tooltip).to_be_visible()
    page.mouse.move(0, 0)
    expect(tooltip).to_be_hidden()
    expect(info).to_be_focused()


def test_repository_info_keyboard_focus_keeps_tooltip_until_dismissed(
    page: Page, service: str
) -> None:
    submit(page, service)
    info = page.get_by_role("button", name="Repository information", exact=True)
    tooltip = page.locator("#repo-tooltip")
    page.locator("#visit-repo").focus()
    page.keyboard.press("Shift+Tab")  # Repository information
    expect(info).to_be_focused()
    expect(tooltip).to_be_visible()
    info.hover()
    page.mouse.move(0, 0)
    expect(tooltip).to_be_visible()
    page.keyboard.press("Escape")
    expect(tooltip).to_be_hidden()
    expect(info).to_be_focused()
    page.keyboard.press("Tab")
    page.keyboard.press("Shift+Tab")
    expect(tooltip).to_be_visible()
    page.keyboard.press("Enter")
    dialog = page.locator("#repo-info-dialog")
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).to_be_hidden()
    expect(info).to_be_focused()
    expect(tooltip).to_be_hidden()
    page.keyboard.press("Tab")
    page.keyboard.press("Shift+Tab")
    expect(tooltip).to_be_visible()
    page.keyboard.press("Tab")
    expect(tooltip).to_be_hidden()


def test_fold_hide_reveal_show_and_note_update_the_treestamp(
    page: Page, service: str
) -> None:
    submit(page, service)
    docs = page.locator('.row[data-path="docs"]')
    docs.locator(".fold").click()
    expect(page.locator('.row[data-path="docs/api.md"]')).to_have_count(0)
    expect(docs.locator(".counts")).to_have_text("(2 files)")

    scripts = page.locator('.row[data-path="scripts"]')
    scripts.hover()
    scripts.focus()
    page.locator("#row-visibility").click()
    expect(page.locator('.row[data-path="scripts"]')).to_have_count(0)
    page.click("#tab-stamp")
    expect(page.locator("#region")).to_contain_text('"scripts"')
    page.click("#tab-editor")

    page.check("#reveal")
    hidden = page.locator('.row.hidden-row[data-path="scripts"]')
    expect(hidden).to_have_count(1)
    hidden.hover()
    hidden.focus()
    page.locator("#row-visibility").click()
    expect(page.locator('.row[data-path="scripts"]:not(.hidden-row)')).to_have_count(1)

    src = page.locator('.row[data-path="src"]')
    src.hover()
    src.focus()
    page.locator("#row-note").click()
    page.fill("#note-text", "application code")
    page.press("#note-text", "Enter")
    expect(src.locator(".note")).to_have_text("# application code")
    page.click("#tab-stamp")
    expect(page.locator("#region")).to_contain_text("src/  # application code")


def test_branch_links_open_and_bad_links_explain(page: Page, service: str) -> None:
    submit(page, service, f"https://github.com/{REPOSITORY}/tree/main")
    page.locator(".wordmark").click()
    page.locator("#entry-url").fill("fixture/repo")
    page.locator("#entry-browse").click()
    page.click("#entry-change-repo")
    page.fill("#entry-url", "not a link")
    page.click("#entry-browse")
    expect(page.locator("#source-load")).to_be_disabled()
    expect(page.locator("#source-create")).to_be_disabled()
    expect(page.locator("#reload-error")).to_be_visible()
    expect(page.locator("#reload-error")).to_contain_text("Accepted forms")


def test_the_address_carries_state_and_reloads_it(page: Page, service: str) -> None:
    submit(page, service)
    page.locator('.row[data-path="docs"] .fold').click()
    expect(page.locator('.row[data-path="docs"] .counts')).to_have_text("(2 files)")
    address = page.url
    assert "#s=" in address
    page.reload()
    page.wait_for_selector("#rows .row")
    expect(page.locator('.row[data-path="docs"] .counts')).to_have_text("(2 files)")


def test_one_count_toggle_controls_full_counts_without_config_settings(
    page: Page, service: str
) -> None:
    submit(page, service)
    page.locator('.row[data-path="docs"] .fold').click()
    counts = page.locator('.row[data-path="docs"] .counts')
    expect(counts).to_have_text("(2 files)")
    page.locator("#show_counts").uncheck()
    expect(counts).to_have_count(0)
    expect(page.locator("#region")).not_to_contain_text("show_counts")
    page.locator("#show_counts").check()
    expect(counts).to_have_text("(2 files)")


@pytest.mark.parametrize("width", [320, 768, 1280])
def test_loaded_document_keeps_tree_and_toolbar_in_place_after_an_edit(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    submit(page, service)
    page.evaluate("document.fonts.ready")
    anchors = page.locator("#rows, #copy, #row-note, #tab-editor")
    geometry = "nodes => nodes.map(node => { const r = node.getBoundingClientRect(); return {x: r.x, y: r.y}; })"
    before = anchors.evaluate_all(geometry)
    page.locator('.row[data-path="docs"] .fold').click()
    expect(page.locator('.row[data-path="docs/api.md"]')).to_have_count(0)
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")
    assert anchors.evaluate_all(geometry) == before
