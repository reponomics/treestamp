"""Editing journeys preserve focus and copy only saved, current output."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Browser, Page, Route, expect  # noqa: E402

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.browser


def open_editor(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo")
    page.wait_for_selector("#rows .row")
    expect(page.locator("#submit")).to_be_enabled()


@pytest.fixture
def touch_page(browser: Browser) -> Iterator[Page]:
    """A device with no pointer to hover with, which must still reach the row actions."""
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, has_touch=True
    )
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()


def test_the_page_opens_on_the_bundled_example_without_a_request(
    page: Page, service: str
) -> None:
    page.route("**/api/preview*", lambda route: route.abort())
    page.goto(service + "/")
    expect(page.locator("#rows .row")).not_to_have_count(0)
    expect(page.locator("#url")).to_have_value("reponomics/reponomics-dashboard")
    expect(page.locator("#error")).to_be_hidden()
    expect(page.locator("#stage-status")).to_be_hidden()
    expect(page.locator("#status")).to_have_text("")


def test_a_failed_load_keeps_the_open_tree(page: Page, service: str) -> None:
    open_editor(page, service)
    page.route(
        "**/api/preview*",
        lambda route: route.fulfill(
            status=503, json={"error": {"message": "Repository unavailable."}}
        ),
    )
    page.fill("#url", "fixture/elsewhere")
    page.click("#submit")
    expect(page.locator("#reload")).to_have_text("Create treestamp")
    page.click("#reload")
    expect(page.locator("#reload-error")).to_contain_text("Repository unavailable.")
    expect(page.locator("#reload-settings")).to_be_visible()
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#copy")).to_be_visible()


@pytest.mark.parametrize("close", ["Cancel", "Escape"])
def test_cancelling_load_preserves_tree_and_restores_source_fields(
    page: Page, service: str, close: str
) -> None:
    open_editor(page, service)
    original_region = page.locator("#region").text_content()
    original_address = page.url
    initial_document = page.locator("#document").input_value()
    initial_root = page.locator("#root").input_value()
    previews: list[str] = []
    page.on(
        "request",
        lambda request: (
            previews.append(request.url) if "/api/preview" in request.url else None
        ),
    )
    page.locator("#url").fill("fixture/another-repository")
    page.locator("#submit").click()
    expect(page.locator("#reload-settings")).to_be_visible()
    expect(page.locator("#reload")).to_have_text("Create treestamp")
    page.locator("#load-tab-document").click()
    page.locator("#document").fill("docs/README.md")
    if close == "Cancel":
        page.locator("#reload-settings").get_by_role(
            "button", name="Cancel", exact=True
        ).click()
    else:
        page.keyboard.press("Escape")
    expect(page.locator("#reload-settings")).to_be_hidden()
    expect(page.locator("#submit")).to_be_focused()
    expect(page.locator("#document")).to_have_value(initial_document)
    expect(page.locator("#root")).to_have_value(initial_root)
    assert page.locator("#region").text_content() == original_region
    assert page.url == original_address
    assert previews == []


def test_dismissing_error_preserves_draft_and_allows_later_errors(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    row = page.locator('.row[data-path="src"]')
    row.locator('[data-action="note"]').click()
    page.locator("#note-text").fill("Preserve this annotation")
    page.locator("#note-save").click()
    expect(row.locator(".note")).to_contain_text("Preserve this annotation")
    original_region = page.locator("#region").text_content()
    original_address = page.url
    page.route(
        "**/api/op",
        lambda route: route.fulfill(
            status=503, json={"error": {"message": "Could not hide this entry."}}
        ),
    )

    row.get_by_role("button", name="Hide", exact=True).click()
    expect(page.locator("#error")).to_contain_text("Could not hide this entry.")
    dismiss = page.get_by_role("button", name="Dismiss error", exact=True)
    dismiss.focus()
    dismiss.press("Enter")
    expect(page.locator("#error")).to_be_hidden()
    expect(page.locator("#url")).to_be_focused()
    expect(row.locator(".note")).to_contain_text("Preserve this annotation")
    assert page.locator("#region").text_content() == original_region
    assert page.url == original_address

    row.get_by_role("button", name="Hide", exact=True).click()
    expect(page.locator("#error")).to_contain_text("Could not hide this entry.")
    expect(dismiss).to_be_visible()


def test_keyboard_fold_preserves_focus(page: Page, service: str) -> None:
    open_editor(page, service)
    fold = page.locator('.row[data-path="docs"] .fold')
    fold.focus()
    fold.press("Enter")
    expect(page.locator('.row[data-path="docs/api.md"]')).to_have_count(0)
    expect(fold).to_be_focused()
    expect(fold).to_have_attribute("aria-expanded", "false")
    fold.press("Enter")
    expect(page.locator('.row[data-path="docs/api.md"]')).to_have_count(1)
    expect(fold).to_be_focused()
    expect(fold).to_have_attribute("aria-expanded", "true")


def test_saving_note_returns_focus_to_its_action(page: Page, service: str) -> None:
    open_editor(page, service)
    row = page.locator('.row[data-path="src"]')
    row.locator('[data-action="note"]').click()
    page.locator("#note-text").fill("application code")
    page.locator("#note-text").press("Enter")
    expect(row.locator(".note")).to_have_text("# application code")
    expect(row.locator('[data-action="note"]')).to_be_focused()


@pytest.mark.parametrize("path", ["", "src"])
def test_note_action_edits_existing_annotation_without_changing_label(
    page: Page, service: str, path: str
) -> None:
    open_editor(page, service)
    row = page.locator(f'.row[data-path="{path}"]')
    action = row.get_by_role("button", name="Note", exact=True)
    action.click()
    page.locator("#note-text").fill("first note")
    page.locator("#note-save").click()
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(row.locator(".note")).to_have_text("# first note")
    action.click()
    expect(page.locator("#note-text")).to_have_value("first note")
    page.locator("#note-text").fill("")
    page.locator("#note-text").press("Enter")
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(row.locator(".note")).to_have_count(0)
    expect(action).to_be_focused()


def test_note_dialog_blocks_copy_until_explicit_save_finishes(
    page: Page, service: str
) -> None:
    from treestamp.document import parse_document

    page.add_init_script("""
        window.copiedBlocks = [];
        Object.defineProperty(navigator, "clipboard", {value: {
            writeText: async text => window.copiedBlocks.push(text)
        }});
        const originalFetch = window.fetch.bind(window);
        window.fetch = async (...args) => {
            const response = await originalFetch(...args);
            if (args[0] === "/api/op") {
                await new Promise(resolve => {
                    window.releaseEdit = resolve;
                    document.documentElement.dataset.editPending = "true";
                });
            }
            return response;
        };
    """)
    open_editor(page, service)
    page.locator('.row[data-path="src"] [data-action="note"]').click()
    note = page.locator("#note-text")
    note.fill("latest note for document")
    assert page.locator("#note-dialog").evaluate("dialog => dialog.matches(':modal')")
    page.locator("#copy").evaluate("button => button.focus()")
    expect(note).to_be_focused()
    assert page.evaluate("window.copiedBlocks") == []
    note.press("Enter")
    expect(page.locator("html")).to_have_attribute("data-edit-pending", "true")
    expect(page.locator("#note-save")).to_be_disabled()
    page.keyboard.press("Escape")
    expect(page.locator("#note-dialog")).to_be_visible()
    assert page.evaluate("window.copiedBlocks") == []
    page.evaluate("window.releaseEdit()")
    expect(page.locator("#note-dialog")).to_be_hidden()
    page.locator("#copy").click()
    expect(page.locator("#copy-label")).to_have_text("Copied")
    copied = page.evaluate("window.copiedBlocks[0]")
    saved = parse_document(copied.encode())
    assert next(n for n in saved.tree.walk() if n.path == "src").annotation == (
        "latest note for document"
    )
    expect(page.locator("#copy-status")).to_have_text("Paste into README.md")


def refuse_export(route: Route) -> None:
    response = route.fetch()
    body = response.json()
    body["region"] = None
    body["tree"] = ""
    body["warnings"] = [
        "A filename is ambiguous in this style; hide it to copy the tree."
    ]
    route.fulfill(response=response, json=body)


@pytest.mark.parametrize("malformed", ["output", "settings", "rows"])
def test_invalid_candidate_keeps_the_accepted_draft(
    page: Page, service: str, malformed: str
) -> None:
    open_editor(page, service)
    original_region = page.locator("#region").text_content()
    original_address = page.url

    def invalid_candidate(route: Route) -> None:
        response = route.fetch()
        body = response.json()
        if malformed == "output":
            body["region"] = None
        elif malformed == "settings":
            body["state"]["curation"]["settings"] = None
        else:
            body["rows"][0]["path"] = None
        route.fulfill(response=response, json=body)

    page.route("**/api/preview*", invalid_candidate)
    page.locator("#url").fill("fixture/replacement")
    page.locator("#submit").click()
    page.locator("#reload").click()
    expect(page.locator("#reload-error")).to_contain_text("previous draft is unchanged")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#region")).to_have_text(original_region)
    assert page.url == original_address
    page.locator("#reload-settings").get_by_role(
        "button", name="Cancel", exact=True
    ).click()
    expect(page.locator("#copy")).to_be_enabled()


def test_note_save_rejects_unprintable_candidate_without_replacing_draft(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    original_region = page.locator("#region").text_content()
    original_address = page.url
    page.route("**/api/op", refuse_export)
    page.locator('.row[data-path="src"] [data-action="note"]').click()
    page.locator("#note-text").fill("last edit")
    page.locator("#note-save").click()
    expect(page.locator("#note-dialog")).to_be_visible()
    expect(page.locator("#note-error")).to_contain_text("previous draft is unchanged")
    expect(page.locator("#region")).to_have_text(original_region)
    assert page.url == original_address
    page.locator("#note-cancel").click()
    expect(page.locator("#copy")).to_be_enabled()


def test_rejected_presentation_restores_accepted_controls(
    page: Page, service: str
) -> None:
    page.set_viewport_size({"width": 1280, "height": 900})
    open_editor(page, service)
    original_region = page.locator("#region").text_content()
    original_address = page.url
    page.route(
        "**/api/op",
        lambda route: route.fulfill(
            status=422,
            json={
                "error": {
                    "code": "curation",
                    "message": "Unsupported source name.",
                }
            },
        ),
    )
    page.locator("#tab-stamp").click()
    page.locator("#style").select_option("ascii")
    expect(page.locator("#error")).to_be_visible()
    expect(page.locator("#style")).to_have_value("unicode")
    page.locator("#show_counts").uncheck()
    expect(page.locator("#show_counts")).to_be_checked()
    expect(page.locator("#region")).to_have_text(original_region)
    assert page.url == original_address


def test_failed_copy_does_not_report_success(page: Page, service: str) -> None:
    page.add_init_script("""
        Object.defineProperty(navigator, "clipboard", {value: {
            writeText: async () => { throw new Error("Clipboard unavailable"); }
        }});
        document.execCommand = () => false;
    """)
    open_editor(page, service)
    page.locator("#copy").click()
    expect(page.locator("#copy-status")).to_have_text("Copy failed")
    expect(page.locator("#copy-label")).to_have_text("Copy treestamp")
    expect(page.locator("#copy")).to_be_enabled()


def test_failed_note_stays_modal_and_does_not_copy_stale_output(
    page: Page, service: str
) -> None:
    page.add_init_script("""
        window.copiedBlocks = [];
        Object.defineProperty(navigator, "clipboard", {value: {
            writeText: async text => window.copiedBlocks.push(text)
        }});
    """)
    open_editor(page, service)
    original_region = page.locator("#region").text_content()
    page.route(
        "**/api/op",
        lambda route: route.fulfill(
            status=503, json={"error": {"message": "Could not save the edit."}}
        ),
    )
    page.locator('.row[data-path="src"] [data-action="note"]').click()
    page.locator("#note-text").fill("unsaved note")
    page.locator("#note-save").click()
    expect(page.locator("#note-dialog .dialog-error")).to_contain_text(
        "Could not save the edit."
    )
    expect(page.locator("#note-dialog")).to_be_visible()
    expect(page.locator("#note-text")).to_be_focused()
    page.locator("#copy").evaluate("button => button.focus()")
    assert page.locator("#note-dialog").evaluate(
        "dialog => dialog.contains(document.activeElement)"
    )
    assert page.locator("#region").text_content() == original_region
    assert page.evaluate("window.copiedBlocks") == []


@pytest.mark.parametrize(
    ("status", "code"), [(503, "unavailable"), (410, "snapshot_unavailable")]
)
def test_reopening_after_a_failed_edit_allows_copy(
    page: Page, service: str, status: int, code: str
) -> None:
    page.add_init_script("""
        window.copiedBlocks = [];
        Object.defineProperty(navigator, "clipboard", {value: {
            writeText: async text => window.copiedBlocks.push(text)
        }});
    """)
    open_editor(page, service)
    original_region = page.locator("#region").text_content()
    page.route(
        "**/api/op",
        lambda route: route.fulfill(
            status=status,
            json={"error": {"code": code, "message": "Could not save the edit."}},
        ),
    )
    page.locator('.row[data-path="docs"] .fold').click()
    expect(page.locator("#error")).to_be_visible()
    page.locator("#copy").click()
    expect(page.locator("#copy-status")).to_have_text("Copied previous draft")
    assert page.evaluate("window.copiedBlocks") == [original_region]
    page.locator("#url").fill("fixture/reopened")
    page.locator("#submit").click()
    page.locator("#reload").click()
    expect(page.locator("#reload-settings")).to_be_hidden()
    expect(page.locator("#url")).to_have_value("fixture/reopened")
    expect(page.locator("#submit")).to_be_enabled()
    page.locator("#copy").click()
    expect(page.locator("#copy-label")).to_have_text("Copied")
    assert len(page.evaluate("window.copiedBlocks")) == 2
    assert (
        page.evaluate("window.copiedBlocks[1]")
        == page.locator("#region").text_content()
    )


@pytest.mark.parametrize("recovery", ["retry", "cancel", "escape"])
def test_failed_note_can_be_retried_or_cancelled(
    page: Page, service: str, recovery: str
) -> None:
    page.add_init_script("""
        window.copiedBlocks = [];
        Object.defineProperty(navigator, "clipboard", {value: {
            writeText: async text => window.copiedBlocks.push(text)
        }});
    """)
    open_editor(page, service)
    row = page.locator('.row[data-path="src"]')
    row.locator('[data-action="note"]').click()
    note = page.locator("#note-text")
    note.fill("unsaved note")
    page.route(
        "**/api/op",
        lambda route: route.fulfill(
            status=503, json={"error": {"message": "Could not save the edit."}}
        ),
    )
    note.press("Enter")
    expect(page.locator("#note-dialog .dialog-error")).to_be_visible()
    expect(note).to_have_value("unsaved note")
    expect(note).to_be_editable()
    expect(note).to_be_focused()
    page.unroute("**/api/op")
    if recovery == "retry":
        note.fill("recovered note")
        note.press("Enter")
        expect(row.locator(".note")).to_have_text("# recovered note")
    else:
        if recovery == "cancel":
            page.locator("#note-cancel").click()
        else:
            note.press("Escape")
        expect(row.locator(".note")).to_have_count(0)
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(row.locator('[data-action="note"]')).to_be_focused()
    page.locator("#copy").click()
    expect(page.locator("#copy-label")).to_have_text("Copied")
    copied = page.evaluate("window.copiedBlocks[0]")
    assert "unsaved note" not in copied
    assert ("recovered note" in copied) == (recovery == "retry")


def test_cancelling_failed_note_preserves_an_earlier_failed_edit(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    page.route(
        "**/api/op",
        lambda route: route.fulfill(
            status=503, json={"error": {"message": "Could not save the edit."}}
        ),
    )
    page.locator('.row[data-path="docs"] .fold').click()
    expect(page.locator("#error")).to_be_visible()
    page.locator('.row[data-path="src"] [data-action="note"]').click()
    note = page.locator("#note-text")
    note.fill("unsaved note")
    with page.expect_response("**/api/op"):
        note.press("Enter")
    expect(note).to_be_editable()
    note.press("Escape")
    expect(page.locator("#note-dialog")).to_be_hidden()
    page.locator("#copy").click()
    expect(page.locator("#copy-status")).to_have_text("Copied previous draft")


@pytest.mark.parametrize("close", ["Cancel", "Escape"])
def test_note_blur_does_not_save_and_cancellation_discards_draft(
    page: Page, service: str, close: str
) -> None:
    open_editor(page, service)
    operations: list[str] = []
    page.on(
        "request",
        lambda request: (
            operations.append(request.url) if request.url.endswith("/api/op") else None
        ),
    )
    row = page.locator('.row[data-path="src"]')
    row.locator('[data-action="note"]').click()
    note = page.locator("#note-text")
    note.fill("unsaved note")
    page.locator("#note-cancel").focus()
    expect(page.locator("#note-dialog")).to_be_visible()
    expect(note).to_have_value("unsaved note")
    assert operations == []
    if close == "Cancel":
        page.locator("#note-cancel").click()
    else:
        page.keyboard.press("Escape")
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(row.locator(".note")).to_have_count(0)
    expect(row.locator('[data-action="note"]')).to_be_focused()
    row.locator('[data-action="note"]').click()
    expect(note).to_have_value("")
    assert operations == []


def test_tree_edit_keeps_opener_status_and_settings_position(
    page: Page, service: str
) -> None:
    page.add_init_script("""
        const originalFetch = window.fetch.bind(window);
        window.fetch = async (...args) => {
            const response = await originalFetch(...args);
            if (args[0] === "/api/op") {
                await new Promise(resolve => {
                    window.releaseEdit = resolve;
                    document.documentElement.dataset.editPending = "true";
                });
            }
            return response;
        };
    """)
    open_editor(page, service)
    settings = page.locator("#settings")
    initial_box = settings.bounding_box()
    assert initial_box is not None
    initial_status = page.locator("#status").text_content() or ""
    page.locator('.row[data-path="docs"] .fold').click()
    expect(page.locator("html")).to_have_attribute("data-edit-pending", "true")
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "true")
    expect(page.locator("#status")).to_have_text(initial_status)
    expect(page.locator("#submit")).to_be_enabled()
    pending_box = settings.bounding_box()
    assert pending_box is not None
    assert pending_box["y"] == pytest.approx(initial_box["y"], abs=1)
    page.evaluate("window.releaseEdit()")
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")
    expect(page.locator("#status")).to_have_text("")
    final_box = settings.bounding_box()
    assert final_box is not None
    assert final_box["y"] == pytest.approx(initial_box["y"], abs=1)


def test_tapping_a_row_offers_its_actions_within_the_pane(
    touch_page: Page, service: str
) -> None:
    """Without hover the row must still offer its actions, and inside the pane:
    the actions used to be laid out past the right edge of the horizontal scroll."""
    page = touch_page
    open_editor(page, service)
    row = page.locator('.row[data-path="src/app.py"]')
    actions = row.locator(".row-actions")
    expect(actions).to_have_css("opacity", "0")

    row.locator(".name").tap()
    assert page.evaluate("document.activeElement.dataset.path") == "src/app.py"
    expect(actions).to_have_css("opacity", "1")
    expect(row.get_by_role("button", name="Hide", exact=True)).to_be_in_viewport(
        ratio=1
    )
    expect(row.get_by_role("button", name="Note", exact=True)).to_be_in_viewport(
        ratio=1
    )


def test_a_tapped_row_keeps_its_actions_until_another_row_takes_them(
    touch_page: Page, service: str
) -> None:
    page = touch_page
    open_editor(page, service)
    first = page.locator('.row[data-path="src/app.py"]')
    second = page.locator('.row[data-path="src/util.py"]')
    first.locator(".name").tap()
    expect(first.locator(".row-actions")).to_have_css("opacity", "1")

    second.locator(".name").tap()
    expect(second.locator(".row-actions")).to_have_css("opacity", "1")
    expect(first.locator(".row-actions")).to_have_css("opacity", "0")


def test_tapping_a_folder_name_both_folds_it_and_offers_its_actions(
    touch_page: Page, service: str
) -> None:
    page = touch_page
    open_editor(page, service)
    docs = page.locator('.row[data-path="docs"]')
    docs.locator(".name").tap()
    expect(page.locator('.row[data-path="docs/api.md"]')).to_have_count(0)
    expect(docs.locator(".name")).to_be_focused()
    expect(docs.locator(".row-actions")).to_have_css("opacity", "1")


@pytest.mark.parametrize("key", ["Enter", "Escape"])
def test_mobile_note_dialog_fits_viewport_and_restores_action_focus(
    page: Page, service: str, key: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    open_editor(page, service)
    docs = page.locator('.row[data-path="docs"]')
    docs.locator('[data-action="note"]').click()
    page.locator("#note-text").fill(
        "A long annotation that makes the tree scroll. " * 3
    )
    page.locator("#note-save").click()
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(docs.locator(".note")).to_be_visible()
    tree = page.locator(".tree-scroll")
    tree.evaluate("element => { element.scrollLeft = element.scrollWidth; }")
    assert tree.evaluate("element => element.scrollLeft > 0")
    row = page.locator('.row[data-path="src"]')
    row.locator('[data-action="note"]').click()
    note = page.locator("#note-text")
    note_box = note.bounding_box()
    dialog_box = page.locator("#note-dialog").bounding_box()
    assert note_box is not None and dialog_box is not None
    assert dialog_box["x"] >= 0
    assert dialog_box["x"] + dialog_box["width"] <= 390
    assert note_box["x"] >= dialog_box["x"]
    assert note_box["x"] + note_box["width"] <= (dialog_box["x"] + dialog_box["width"])
    note.fill("mobile annotation")
    note.press(key)
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(row.locator('[data-action="note"]')).to_be_focused()
    if key == "Enter":
        expect(row.locator(".note")).to_have_text("# mobile annotation")
    else:
        expect(row.locator(".note")).to_have_count(0)


def test_view_tabs_support_arrow_home_end_navigation(page: Page, service: str) -> None:
    open_editor(page, service)
    tabs = {name: page.locator(f"#tab-{name}") for name in ["editor", "stamp", "info"]}
    tabs["editor"].focus()
    for key, selected in [
        ("ArrowRight", "stamp"),
        ("ArrowRight", "info"),
        ("ArrowRight", "editor"),
        ("ArrowLeft", "info"),
        ("ArrowLeft", "stamp"),
        ("Home", "editor"),
        ("End", "info"),
    ]:
        page.keyboard.press(key)
        expect(tabs[selected]).to_be_focused()
        for name, tab in tabs.items():
            active = name == selected
            expect(tab).to_have_attribute("aria-selected", str(active).lower())
            expect(tab).to_have_js_property("tabIndex", 0 if active else -1)
            expect(page.locator(f"#{name}-panel")).to_have_js_property(
                "hidden", not active
            )


def test_expired_saved_link_does_not_export_an_unvalidated_placeholder(
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
            status=410,
            json={
                "error": {
                    "code": "snapshot_unavailable",
                    "message": "Snapshot expired.",
                }
            },
        ),
    )
    page.reload()
    expect(page.locator("#error")).to_contain_text("Load the repository URL again")
    expect(page.locator("#rows .row")).to_have_count(0)
    page.locator("#copy").evaluate("button => button.click()")
    expect(page.locator("#copy-status")).to_have_text("No draft to copy")
    expect(page.locator("#copy")).to_be_disabled()
    assert page.evaluate("window.copiedBlocks") == []
