"""Responsive layout contracts for the repository editor."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


def assert_no_page_overflow(page: Page) -> None:
    """Long tree paths may scroll locally, but the whole page must fit."""
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def assert_row_actions_in_view(page: Page) -> None:
    """Shared actions stay above the tree, never covering a row's text."""
    docs = page.locator('.row[data-path="docs"]')
    docs.focus()
    expect(page.locator("#selected-path")).to_contain_text("docs")
    tree_bounds = page.locator(".tree-scroll").bounding_box()
    assert tree_bounds is not None
    expect(page.locator("#rows .row-actions")).to_have_count(0)
    for selector in ["#row-note", "#row-visibility"]:
        action_bounds = page.locator(selector).bounding_box()
        assert action_bounds is not None
        assert action_bounds["x"] >= tree_bounds["x"]
        assert (
            action_bounds["x"] + action_bounds["width"]
            <= tree_bounds["x"] + tree_bounds["width"]
        )
        assert action_bounds["y"] + action_bounds["height"] <= tree_bounds["y"]


@pytest.mark.parametrize(
    "width", [320, 390, 767, 768, 900, 1023, 1024, 1025, 1280, 1440, 1920]
)
def test_workspace_layout(page: Page, service: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(service + "/")
    page.evaluate("document.fonts.ready")
    assert_no_page_overflow(page)
    docs_link = page.get_by_role(
        "link", name="treestamp on GitHub (opens in a new tab)"
    )
    expect(docs_link).to_be_visible()
    expect(docs_link).to_be_in_viewport(ratio=1)
    expect(docs_link.locator(".control-icon")).to_have_count(2)
    for icon in docs_link.locator(".control-icon").all():
        expect(icon).to_be_visible()
    # The icon-only GitHub link keeps its button treatment when the header wraps.
    expect(docs_link).to_have_css("border-top-style", "solid")
    expect(docs_link).to_have_css("text-decoration-line", "none")
    assert docs_link.evaluate(
        "element => { const style = getComputedStyle(element); "
        "return style.borderTopColor !== 'rgba(0, 0, 0, 0)' "
        "&& style.backgroundColor !== 'rgba(0, 0, 0, 0)'; }"
    )
    docs_bounds = docs_link.bounding_box()
    assert docs_bounds is not None
    assert docs_bounds["height"] >= (36 if width < 1024 else 44)
    theme_toggle = page.locator("#theme-toggle")
    theme_toggle.click()
    expect(theme_toggle).to_have_text("Light mode")
    expect(docs_link).to_be_in_viewport(ratio=1)
    assert_no_page_overflow(page)
    theme_toggle.click()

    page.fill("#entry-url", "fixture/repo")
    page.click("#entry-browse")
    page.locator('.source-row[data-path="README.md"]').click()
    page.click("#source-load")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")

    controls = page.locator(".controls").bounding_box()
    stage = page.locator("#result").bounding_box()
    assert controls is not None and stage is not None
    if width >= 1024:
        # Two panes fill the window; the settings sit under the repository field.
        assert controls["x"] + controls["width"] <= stage["x"]
        assert controls["y"] == pytest.approx(stage["y"], abs=1)
        assert controls["height"] == pytest.approx(stage["height"], abs=1)
        assert stage["y"] + stage["height"] <= 900
        if width >= 1280:
            assert stage["width"] >= 800
        assert page.evaluate(
            "document.documentElement.scrollHeight <= window.innerHeight"
        )
    else:
        assert controls["y"] + controls["height"] <= stage["y"]
        assert controls["width"] == pytest.approx(stage["width"], abs=1)
    if width >= 1024:
        expect(page.locator("#show_counts")).to_be_visible()
        expect(page.locator("#reveal")).to_be_visible()
        expect(page.locator(".settings-open")).to_be_hidden()
        expect(page.locator(".attribution")).to_be_visible()
    else:
        # Phones and tablets keep settings out of the tree workspace.
        expect(page.locator("#show_counts")).to_be_hidden()
        page.click(".settings-open")
        expect(page.locator("#show_counts")).to_be_visible()
        page.click("#settings .settings-head button")
        expect(page.locator("#show_counts")).to_be_hidden()
    assert_no_page_overflow(page)
    assert_row_actions_in_view(page)

    page.click("#tab-stamp")
    expect(page.locator("#region")).to_be_visible()
    assert_no_page_overflow(page)


@pytest.mark.parametrize(("width", "height"), [(1280, 800), (1440, 900)])
def test_desktop_sidebar_fits_with_a_repository_summary(
    page: Page, service: str, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(service + "/")
    page.locator("#explore-example").click()
    expect(page.locator("#rows .row").first).to_be_visible()
    page.evaluate("document.fonts.ready")
    controls = page.locator(".controls")
    assert controls.evaluate(
        "element => element.scrollHeight <= element.clientHeight"
    ), controls.evaluate(
        'element => ({scrollHeight: element.scrollHeight, clientHeight: element.clientHeight, children: [...element.querySelectorAll("#form, #form > *, .repo-links, .repo-row, #settings, #settings > *")].map(child => ({id: child.id, class: child.className, rect: child.getBoundingClientRect().toJSON()}))})'
    )
    expect(page.locator("#reveal")).to_be_in_viewport(ratio=1)
    expect(page.locator("#url")).to_be_hidden()
    expect(page.locator("#active-repository")).to_have_text("reponomics/treestamp")
    expect(page.locator("#repo-info")).to_be_in_viewport(ratio=1)


def test_a_tall_tree_scrolls_inside_its_pane_on_a_wide_window(
    page: Page, service: str
) -> None:
    # A window too short for nine rows: the pane scrolls, the page does not.
    page.set_viewport_size({"width": 1280, "height": 420})
    page.goto(service + "/")
    page.fill("#entry-url", "fixture/repo")
    page.click("#entry-browse")
    page.locator('.source-row[data-path="README.md"]').click()
    page.click("#source-load")
    expect(page.locator("#rows .row")).to_have_count(9)
    assert page.evaluate("document.documentElement.scrollHeight <= window.innerHeight")
    tree = page.locator(".tree-scroll")
    assert tree.evaluate("element => element.scrollHeight > element.clientHeight")
    expect(page.locator("#copy")).to_be_in_viewport(ratio=1)
    page.locator("#reveal").scroll_into_view_if_needed()
    expect(page.locator("#reveal")).to_be_in_viewport(ratio=1)


def test_the_settings_sheet_closes_when_the_window_widens(
    page: Page, service: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(service + "/")
    page.locator("#explore-example").click()
    expect(page.locator("#rows .row")).not_to_have_count(0)
    page.click(".settings-open")
    assert page.evaluate("document.getElementById('settings').matches(':popover-open')")
    page.set_viewport_size({"width": 768, "height": 800})
    expect(page.locator("#settings:popover-open")).to_have_count(1)
    expect(page.locator(".settings-open")).to_be_visible()
    page.set_viewport_size({"width": 1024, "height": 800})
    expect(page.locator("#settings:popover-open")).to_have_count(0)
    expect(page.locator("#show_counts")).to_be_visible()
    expect(page.locator(".settings-open")).to_be_hidden()


@pytest.mark.parametrize("width", [390, 1024])
def test_long_note_keeps_other_row_actions_in_view(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(service + "/")
    page.fill("#entry-url", "fixture/repo")
    page.click("#entry-browse")
    page.locator('.source-row[data-path="README.md"]').click()
    page.click("#source-load")
    expect(page.locator("#rows .row")).to_have_count(9)

    src = page.locator('.row[data-path="src"]')
    src.locator(".name").hover()
    src.focus()
    page.locator("#row-note").click()
    note = (
        "A lengthy annotation describing the application source and supporting modules. "
        * 3
    )
    page.locator("#note-text").fill(note)
    page.locator("#note-text").press("Enter")
    expect(src.locator(".note")).to_have_text("# " + note.strip())

    tree = page.locator(".tree-scroll")
    assert tree.evaluate("element => element.scrollWidth > element.clientWidth")
    tree.evaluate("element => { element.scrollLeft = 0; }")
    assert_row_actions_in_view(page)
    assert_no_page_overflow(page)


@pytest.mark.parametrize(
    # The compact completion status and first tree entries fit in the
    # first viewport alongside the compact mobile header.
    ("width", "height", "tree_top_limit"),
    [(1280, 800, 270), (390, 844, 540)],
)
def test_loaded_tree_is_available_in_first_viewport(
    page: Page, service: str, width: int, height: int, tree_top_limit: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(service + "/")
    page.fill("#entry-url", "fixture/repo")
    page.click("#entry-browse")
    page.locator('.source-row[data-path="README.md"]').click()
    page.click("#source-load")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")
    page.evaluate("document.fonts.ready")
    # Clicking controls may scroll automatically; assess the actual page start.
    page.evaluate("window.scrollTo(0, 0)")

    tree = page.locator(".tree-scroll").bounding_box()
    first_row = page.locator("#rows .row").first
    assert tree is not None
    assert 0 <= tree["y"] <= tree_top_limit + 1  # Allow subpixel layout rounding.
    expect(page.locator(".stage-head")).to_be_in_viewport(ratio=1)
    expect(first_row).to_be_in_viewport(ratio=1)
    expect(page.locator("#rows .row").nth(2)).to_be_in_viewport(ratio=1)

    if width >= 1024:
        row_bounds = first_row.bounding_box()
        assert row_bounds is not None
        assert height - tree["y"] >= 12 * row_bounds["height"]


@pytest.mark.parametrize("width", [320, 390, 1280])
def test_editor_dialogs_fit_and_keep_actions_reachable(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 640})
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#tui-mode")).to_be_visible()
    assert_no_page_overflow(page)

    page.locator('.row[data-path="docs"]').focus()
    page.locator("#row-note").click()
    dialog = page.locator("#note-dialog")
    expect(dialog).to_be_visible()
    expect(page.locator("#note-text")).to_be_focused()
    expect(page.locator("#note-save")).to_be_in_viewport(ratio=1)
    assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth")
    page.locator("#note-cancel").click()

    page.locator("#tui-help").click()
    dialog = page.locator("#keymap-dialog")
    expect(dialog).to_be_visible()
    assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth")
    dialog.locator(".dialog-hint").scroll_into_view_if_needed()
    expect(dialog.locator(".dialog-hint")).to_be_in_viewport(ratio=1)
    page.keyboard.press("Escape")

    page.locator(".wordmark").click()
    page.locator("#entry-url").fill("fixture/repo")
    page.locator("#entry-browse").click()
    dialog = page.locator("#reload-settings")
    expect(page.locator("#source-create")).to_be_enabled()
    assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth")
    for selector in ("#source-create", "#source-load"):
        expect(page.locator(selector)).to_be_in_viewport(ratio=1)
    assert_no_page_overflow(page)


@pytest.mark.parametrize(
    ("width", "height"), [(390, 844), (320, 568), (768, 1024), (900, 600)]
)
def test_phone_and_tablet_example_give_most_of_the_viewport_to_the_tree(
    page: Page, service: str, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(service + "/")
    page.locator("#explore-example").click()
    expect(page.locator("#rows .row")).not_to_have_count(0)
    page.evaluate("document.fonts.ready")
    tree = page.locator(".tree-scroll").bounding_box()
    assert tree is not None
    assert tree["height"] > height / 2
    assert tree["y"] + tree["height"] <= height
    assert page.evaluate("document.documentElement.scrollHeight <= innerHeight")
    assert_no_page_overflow(page)
    for selector in [".wordmark", "#repo-info", "#visit-repo"]:
        expect(page.locator(selector)).to_be_in_viewport(ratio=1)
    page.locator('.row[data-path="src/treestamp"] .fold').click()
    expect(page.locator('.row[data-path^="src/treestamp/"]').first).to_be_visible()
    page.locator("#rows .row").last.scroll_into_view_if_needed()
    expect(page.locator("#row-note")).to_be_in_viewport(ratio=1)
    expect(page.locator("#row-visibility")).to_be_in_viewport(ratio=1)
    assert page.evaluate("window.scrollY") == 0


@pytest.mark.parametrize("width", [390, 768, 1280])
def test_settings_keep_discard_below_the_editing_options(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    if width < 1024:
        page.locator(".settings-open").click()
    settings = page.locator("#settings")
    expect(settings).to_be_visible()
    options = settings.locator(".settings-group").bounding_box()
    discard = page.locator("#reset-tree").bounding_box()
    assert options is not None and discard is not None
    assert discard["y"] >= options["y"] + options["height"]
    for selector in [
        "#show_counts",
        "#attribution",
        "#reveal",
        "#show-all",
        "#reset-tree",
    ]:
        expect(page.locator(selector)).to_be_in_viewport(ratio=1)
    assert settings.evaluate("node => node.scrollWidth <= node.clientWidth")
    assert_no_page_overflow(page)
