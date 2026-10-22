"""Optional TUI controls leave ordinary browser and form interactions intact."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

from .test_navigation import delay_next_operation, row  # noqa: E402

pytestmark = pytest.mark.browser


def open_editor(page: Page, service: str, *, tui_mode: bool = True) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#submit")).to_be_enabled()
    expect(page.locator("#tui-mode")).to_have_attribute("aria-pressed", "false")
    if tui_mode:
        page.locator("#tui-mode").click()
        expect(page.locator("#tui-mode")).to_have_attribute("aria-pressed", "true")


def test_tui_mode_starts_off_and_preserves_native_button_activation(
    page: Page, service: str
) -> None:
    open_editor(page, service, tui_mode=False)
    docs = row(page, "docs")
    docs.focus()
    for key in [
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
        "Home",
        "End",
        "PageUp",
        "PageDown",
        " ",
        "a",
        "h",
        "H",
        "S",
        "f",
        "?",
    ]:
        allowed = docs.evaluate(
            """(element, key) => element.dispatchEvent(new KeyboardEvent(
                "keydown", {key, bubbles: true, cancelable: true}
            ))""",
            key,
        )
        assert allowed, f"TUI-mode off consumed {key}"
        expect(docs).to_be_focused()
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(page.locator("#keymap-dialog")).to_be_hidden()

    docs.locator(".fold").press("Space")
    expect(row(page, "docs/api.md")).to_have_count(0)
    docs.locator(".fold").press("Enter")
    expect(row(page, "docs/api.md")).to_have_count(1)
    docs.get_by_role("button", name="Note", exact=True).press("Space")
    expect(page.locator("#note-text")).to_be_focused()
    page.locator("#note-text").press("Escape")
    expect(docs.get_by_role("button", name="Note", exact=True)).to_be_focused()


def test_tui_mode_leaves_modified_and_composing_keys_to_the_browser(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    docs = row(page, "docs")
    docs.focus()
    for modifier in ["altKey", "ctrlKey", "metaKey", "isComposing"]:
        for key in ["ArrowRight", "a", "h", "H", "S", "f", "?"]:
            allowed = docs.evaluate(
                """(element, options) => element.dispatchEvent(new KeyboardEvent(
                    "keydown", {...options, bubbles: true, cancelable: true}
                ))""",
                {"key": key, modifier: True},
            )
            assert allowed, f"TUI-mode consumed {modifier}+{key}"
    expect(docs).to_be_focused()
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(page.locator("#keymap-dialog")).to_be_hidden()


@pytest.mark.parametrize("save_with", ["Enter", "Save"])
def test_tui_annotation_uses_dialog_and_preserves_native_text_input(
    page: Page, service: str, save_with: str
) -> None:
    open_editor(page, service)
    docs = row(page, "docs")
    docs.focus()
    page.keyboard.press("a")
    note = page.locator("#note-text")
    expect(note).to_be_focused()
    note.press_sequentially("ahHSf?")
    expect(note).to_have_value("ahHSf?")
    expect(page.locator("#keymap-dialog")).to_be_hidden()
    expect(page.locator("#reveal")).not_to_be_checked()
    expect(page.locator("#rows .row")).to_have_count(9)
    if save_with == "Enter":
        note.press("Enter")
    else:
        page.locator("#note-save").click()
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(docs.locator(".note")).to_have_text("# ahHSf?")
    expect(docs).to_be_focused()
    page.keyboard.press("a")
    expect(note).to_have_value("ahHSf?")
    note.fill("discard this change")
    page.locator("#note-cancel").click()
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(docs.locator(".note")).to_have_text("# ahHSf?")
    expect(docs).to_be_focused()

    repository = page.locator("#url")
    repository.fill("")
    repository.press_sequentially("ahHSf?")
    expect(repository).to_have_value("ahHSf?")
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(page.locator("#keymap-dialog")).to_be_hidden()


def test_tui_hide_and_reveal_keep_view_state_separate_from_output(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    docs = row(page, "docs")
    docs.focus()
    page.keyboard.press("h")
    expect(docs).to_have_count(0)
    expect(row(page, "scripts")).to_be_focused()
    hidden_output = page.locator("#region").inner_text()
    page.keyboard.press("Shift+H")
    expect(page.locator("#reveal")).to_be_checked()
    expect(docs).to_have_class("row dir hidden-row")
    expect(page.locator("#region")).to_have_text(hidden_output)
    docs.focus()
    page.keyboard.press("h")
    expect(docs).to_have_class("row dir")
    expect(docs).to_be_focused()
    page.keyboard.press("Shift+H")
    expect(page.locator("#reveal")).not_to_be_checked()
    expect(page.locator("#rows .row")).to_have_count(9)
    root = row(page, "")
    root.focus()
    page.keyboard.press("h")
    expect(root).to_be_focused()
    expect(page.locator("#rows .row")).to_have_count(9)


def test_tui_help_opens_from_question_mark_and_button_and_restores_focus(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    docs = row(page, "docs")
    docs.focus()
    page.keyboard.press("Shift+?")
    help_dialog = page.get_by_role("dialog", name="Keyboard shortcuts", exact=True)
    expect(help_dialog).to_be_visible()
    expect(help_dialog).to_contain_text("TUI-mode")
    page.keyboard.press("Escape")
    expect(help_dialog).to_be_hidden()
    expect(docs).to_be_focused()

    page.locator("#tui-mode").click()
    page.get_by_role("button", name="Keyboard shortcuts", exact=True).click()
    expect(help_dialog).to_be_visible()
    help_dialog.get_by_role("button", name="Close", exact=True).click()
    expect(help_dialog).to_be_hidden()
    expect(page.locator("#tui-help")).to_be_focused()


def test_tui_annotation_waits_for_pending_tree_edits(page: Page, service: str) -> None:
    open_editor(page, service)
    delay_next_operation(page)
    docs = row(page, "docs")
    docs.focus()
    page.keyboard.press("ArrowLeft")
    expect(page.locator("html")).to_have_attribute("data-navigation-pending", "true")
    page.keyboard.press("a")
    expect(page.locator("#note-dialog")).to_be_hidden()
    page.evaluate("window.releaseNavigation()")
    expect(row(page, "docs/api.md")).to_have_count(0)
    expect(page.locator("#note-text")).to_be_focused()
    page.locator("#note-text").fill("after collapse")
    page.locator("#note-save").click()
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(docs.locator(".note")).to_have_text("# after collapse")
    expect(docs).to_be_focused()


def test_tui_mode_off_cancels_commands_waiting_behind_an_edit(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    delay_next_operation(page)
    docs = row(page, "docs")
    docs.focus()
    page.keyboard.press("ArrowLeft")
    expect(page.locator("html")).to_have_attribute("data-navigation-pending", "true")
    for key in ["ArrowRight", "a", "h", "Shift+H", "Shift+S", "f", "Shift+?"]:
        page.keyboard.press(key)
    page.locator("#tui-mode").click()
    expect(page.locator("#tui-mode")).to_have_attribute("aria-pressed", "false")
    docs.focus()
    page.evaluate("window.releaseNavigation()")
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")
    expect(docs).to_be_focused()
    expect(row(page, "docs/api.md")).to_have_count(0)
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(page.locator("#keymap-dialog")).to_be_hidden()
    expect(page.locator("#reveal")).not_to_be_checked()


def test_tui_repeated_reveal_commands_use_the_latest_view_state(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    delay_next_operation(page)
    row(page, "docs").focus()
    page.keyboard.press("Shift+H")
    expect(page.locator("html")).to_have_attribute("data-navigation-pending", "true")
    page.keyboard.press("Shift+H")
    with page.expect_request("**/api/op") as second_operation:
        page.evaluate("window.releaseNavigation()")
    assert second_operation.value.post_data_json["reveal"] is False
    expect(page.locator("#reveal")).not_to_be_checked()
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(row(page, "docs")).to_be_focused()


def test_tui_repeated_hide_commands_follow_the_repaired_selection(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    delay_next_operation(page)
    row(page, "docs").focus()
    page.keyboard.press("h")
    expect(page.locator("html")).to_have_attribute("data-navigation-pending", "true")
    page.keyboard.press("h")
    with page.expect_request("**/api/op") as second_operation:
        page.evaluate("window.releaseNavigation()")
    assert second_operation.value.post_data_json["op"] == {
        "type": "hide",
        "path": "scripts",
        "text": "",
    }
    expect(row(page, "docs")).to_have_count(0)
    expect(row(page, "scripts")).to_have_count(0)
    expect(row(page, "src")).to_be_focused()


def test_tui_held_character_commands_do_not_repeat_edits(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    docs = row(page, "docs")
    docs.focus()
    for key in ["a", "h", "H", "S", "f", "?"]:
        docs.dispatch_event("keydown", {"key": key, "repeat": True, "bubbles": True})
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#note-dialog")).to_be_hidden()
    expect(page.locator("#keymap-dialog")).to_be_hidden()
    expect(page.locator("#reveal")).not_to_be_checked()
    expect(page.locator("#show_counts")).to_be_checked()
    expect(docs).to_be_focused()


def test_tui_repeated_count_commands_advance_after_the_pending_response(
    page: Page, service: str
) -> None:
    open_editor(page, service)
    delay_next_operation(page)
    row(page, "docs").focus()
    page.keyboard.press("f")
    expect(page.locator("html")).to_have_attribute("data-navigation-pending", "true")
    page.keyboard.press("f")
    with page.expect_request("**/api/op") as second_operation:
        page.evaluate("window.releaseNavigation()")
    settings = second_operation.value.post_data_json["state"]["curation"]["settings"]
    assert settings["show_counts"] is True
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")
    expect(page.locator("#show_counts")).to_be_checked()
    expect(row(page, "docs")).to_be_focused()


@pytest.mark.parametrize("reveal_hidden", [False, True])
def test_show_all_restores_output_without_changing_folds_or_reveal(
    page: Page, service: str, reveal_hidden: bool
) -> None:
    open_editor(page, service)
    docs = row(page, "docs")
    docs.focus()
    page.keyboard.press("ArrowLeft")
    expect(row(page, "docs/api.md")).to_have_count(0)
    row(page, "src/app.py").focus()
    page.keyboard.press("h")
    expect(row(page, "src/app.py")).to_have_count(0)
    row(page, "src").focus()
    page.keyboard.press("h")
    expect(row(page, "src")).to_have_count(0)
    root = row(page, "")
    root.focus()
    if reveal_hidden:
        page.keyboard.press("Shift+H")
        expect(page.locator("#reveal")).to_be_checked()
    with page.expect_response(
        lambda response: (
            response.url.endswith("/api/op")
            and response.request.post_data_json["op"]["type"] == "unhide_all"
        )
    ) as response:
        page.keyboard.press("Shift+S")
    state = response.value.json()["state"]["curation"]
    assert state["hidden"] == []
    expect(root).to_be_focused()
    expect(row(page, "src/app.py")).to_be_visible()
    expect(row(page, "README.md")).to_be_visible()
    expect(row(page, "docs/api.md")).to_have_count(0)
    expect(page.locator("#reveal")).to_be_checked(checked=reveal_hidden)
    expect(page.locator("#show-all")).to_be_disabled()
    expect(page.locator("#region")).to_contain_text("app.py")
    expect(page.locator("#region")).not_to_contain_text('"excluded_paths"')


@pytest.mark.parametrize("width", [390, 1280])
def test_show_all_button_works_without_tui_mode(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    open_editor(page, service, tui_mode=False)
    if width < 1024:
        page.locator(".settings-open").click()
    with page.expect_response("**/api/op") as response:
        page.get_by_role("button", name="Unhide all", exact=True).click()
    assert response.value.json()["state"]["curation"]["hidden"] == []
    expect(page.locator("#show-all")).to_be_disabled()
    expect(page.locator("#reveal")).not_to_be_checked()
    expect(page.locator("#tui-mode")).to_have_attribute("aria-pressed", "false")
    expect(row(page, "README.md")).to_have_count(1)


def test_tui_count_key_toggles_one_boolean(page: Page, service: str) -> None:
    open_editor(page, service)
    docs = row(page, "docs")
    docs.focus()
    for shown in (False, True):
        with page.expect_request("**/api/op") as operation:
            page.keyboard.press("f")
        assert (
            operation.value.post_data_json["state"]["curation"]["settings"][
                "show_counts"
            ]
            is shown
        )
        assert operation.value.post_data_json["op"]["type"] == "present"
        expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")
        expect(page.locator("#show_counts")).to_be_checked(checked=shown)
        expect(docs).to_be_focused()
