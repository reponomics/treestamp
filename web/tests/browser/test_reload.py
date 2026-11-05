"""Opening replaces a draft only after success, with a fixed captured snapshot."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


def add_note(page: Page, text: str) -> None:
    row = page.locator('.row[data-path="docs"]')
    row.locator('[data-action="note"]').click()
    page.locator("#note-text").fill(text)
    page.locator("#note-text").press("Enter")
    expect(row.locator(".note")).to_have_text(f"# {text}")


@pytest.mark.parametrize("close", ["Cancel", "Escape"])
@pytest.mark.parametrize("width", [390, 1280])
def test_cancelled_open_preserves_curation_and_source(
    page: Page, service: str, close: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    add_note(page, "keep current work")
    original = page.locator("#region").text_content()
    address = page.url
    page.locator("#submit").click()
    page.locator("#load-tab-new").click()
    page.locator("#root").fill("src")
    if close == "Cancel":
        page.get_by_role("button", name="Cancel", exact=True).click()
    else:
        page.keyboard.press("Escape")
    expect(page.locator("#reload-settings")).to_be_hidden()
    expect(page.locator("#submit")).to_be_focused()
    expect(page.locator("#region")).to_have_text(original)
    assert page.url == address
    with page.expect_request("**/api/op") as request:
        add_note(page, "continue current work")
    assert request.value.post_data_json["root"] == "."
    assert request.value.post_data_json["document"] == "README.md"


def test_failed_explicit_open_preserves_draft_and_cannot_initialize_new(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    add_note(page, "existing work")
    original = page.locator("#region").text_content()
    address = page.url
    page.locator("#submit").click()
    page.locator("#document").fill("missing.md")
    page.locator("#reload").click()
    expect(page.locator("#reload-error")).to_be_visible()
    expect(page.locator("#reload-settings")).to_be_visible()
    expect(page.locator("#reload")).to_be_enabled()
    expect(page.locator("#region")).to_have_text(original)
    assert page.url == address
    page.get_by_role("button", name="Cancel", exact=True).click()
    add_note(page, "work after failed open")


@pytest.mark.parametrize("root", ["src", "./src", "./src/"])
def test_new_root_is_repository_relative_and_initial_depth_is_one(
    page: Page, service: str, root: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.locator("#submit").click()
    page.locator("#load-tab-new").click()
    page.locator("#root").fill(root)
    with page.expect_response("**/api/preview*") as response:
        page.locator("#reload").click()
    assert response.value.ok
    data = response.value.json()
    assert data["loaded"] is False
    assert data["root"] == "src"
    assert data["document"] == ""
    assert response.value.request.post_data_json == {
        "url": "fixture/repo",
        "root": root,
        "document": "",
    }
    expect(page.locator("#rows .row")).to_have_count(3)
    expect(page.locator("#region")).to_contain_text('root = "src"')
    expect(page.locator("#loaded-note")).to_be_hidden()
    expect(page.locator("#stage-status")).to_be_hidden()
    expect(page.locator("#status")).to_have_text("")
    address = page.url
    page.reload()
    expect(page.locator("#rows .row")).to_have_count(3)
    expect(page.locator("#root")).to_have_value("src")
    assert page.url == address


def test_successful_reopen_discards_unwritten_notes_hiding_and_folds(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    original = page.locator("#region").text_content()
    add_note(page, "discard this")
    page.locator('.row[data-path="docs"] .fold').click()
    page.locator('.row[data-path="scripts"]').get_by_role(
        "button", name="Hide", exact=True
    ).click()
    expect(page.locator("#stage-status")).to_be_hidden()
    page.locator("#submit").click()
    expect(page.locator("#reload-settings")).to_contain_text(
        "Current changes in the editor will be discarded"
    )
    expect(page.locator("#root")).to_be_hidden()
    with page.expect_response("**/api/preview*") as response:
        page.locator("#reload").click()
    assert response.value.ok
    assert response.value.json()["state"]["revision"] == 0
    expect(page.locator("#region")).to_have_text(original)
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#stage-status")).to_have_text("Treestamp is up to date")


def test_edits_and_count_toggles_retain_the_captured_commit(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    commit = page.locator("#repo-info-dialog [data-repo-commit]").text_content()
    requests: list[dict] = []
    previews: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.post_data_json)
            if request.url.endswith("/api/op")
            else None
        ),
    )
    page.on(
        "request",
        lambda request: (
            previews.append(request.url) if "/api/preview" in request.url else None
        ),
    )
    page.locator('.row[data-path="docs"] .fold').click()
    expect(page.locator('.row[data-path="docs"] .counts')).to_have_text("(2 files)")
    page.locator("#show_counts").uncheck()
    expect(page.locator('.row[data-path="docs"] .counts')).to_have_count(0)
    page.locator("#show_counts").check()
    expect(page.locator('.row[data-path="docs"] .counts')).to_have_text("(2 files)")
    assert requests and all(request["ref"] == commit for request in requests)
    assert all(request["state"]["source"]["commit"] == commit for request in requests)
    assert previews == []


def test_reopen_retains_unchanged_byte_document_identity(
    page: Page, service: str
) -> None:
    """The form can display byte names without converting them back to Unicode."""
    document = {"git_bytes": "646f63ff2e6d64"}
    data: dict = {}

    def initial(route):
        nonlocal data
        response = route.fetch()
        data = response.json()
        data["document"] = document
        data["state"]["source"]["document"] = document
        route.fulfill(response=response, json=data)

    page.route("**/api/preview?*", initial)
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.route("**/api/preview", lambda route: route.fulfill(json=data))
    page.locator("#submit").click()
    expect(page.locator("#document")).to_have_value("doc�.md")
    with page.expect_request("**/api/preview") as request:
        page.locator("#reload").click()
    assert request.value.method == "POST"
    assert request.value.post_data_json["document"] == document
    expect(page.locator("#reload-settings")).to_be_hidden()


@pytest.mark.parametrize(
    "mode,field,value",
    [("new", "root", " src "), ("document", "document", " README.md ")],
)
def test_source_selection_keeps_significant_path_whitespace(
    page: Page, service: str, mode: str, field: str, value: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.route(
        "**/api/preview",
        lambda route: route.fulfill(
            status=404, json={"error": {"message": "Exact path not found."}}
        ),
    )
    page.locator("#submit").click()
    page.locator(f"#load-tab-{mode}").click()
    page.locator(f"#{field}").fill(value)
    with page.expect_request("**/api/preview") as request:
        page.locator("#reload").click()
    assert request.value.post_data_json[field] == value
    if mode == "document":
        assert "root" not in request.value.post_data_json
    else:
        assert request.value.post_data_json["document"] == ""
    expect(page.locator("#reload-error")).to_contain_text("Exact path not found.")


@pytest.mark.parametrize("width", [390, 1280])
def test_load_tabs_separate_document_and_root_selection(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(service + "/")
    expect(page.locator("#rows .row").first).to_be_visible()
    expect(page.locator("#stage-status")).to_be_hidden()
    expect(page.locator("#status")).to_have_text("")
    page.locator("#url").fill("fixture/repo")
    page.locator("#submit").click()
    new = page.get_by_role("tab", name="New document", exact=True)
    load = page.get_by_role("tab", name="Load document", exact=True)
    expect(new).to_have_attribute("aria-selected", "true")
    expect(page.locator("#root")).to_be_visible()
    expect(page.locator("#document")).to_be_hidden()
    load.click()
    expect(load).to_have_attribute("aria-selected", "true")
    expect(page.locator("#root")).to_be_hidden()
    expect(page.locator("#document")).to_be_visible()
    expect(page.locator("#document")).to_have_value("README.md")
    expect(page.locator("#load-panel-document")).to_contain_text(
        "Opening an existing treestamp will show any updates based on the current project state"
    )
    expect(page.locator("#reload-settings")).to_contain_text(
        "Current changes in the editor will be discarded"
    )
    with page.expect_request("**/api/preview") as request:
        page.locator("#reload").click()
    assert request.value.post_data_json == {
        "url": "fixture/repo",
        "document": "README.md",
    }
    expect(page.locator("#reload-settings")).to_be_hidden()
    expect(page.locator("#stage-status")).to_have_text("Treestamp is up to date")
    page.locator("#submit").click()
    expect(load).to_have_attribute("aria-selected", "true")


def test_load_document_requires_a_path_before_requesting(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.locator("#submit").click()
    page.locator("#document").fill("")
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    page.locator("#reload").click()
    expect(page.locator("#document")).to_be_focused()
    assert page.locator("#document").evaluate("input => input.validity.valueMissing")
    expect(page.locator("#reload-settings")).to_be_visible()
    assert not any("/api/preview" in url for url in requests)


def test_load_tabs_support_keyboard_navigation(page: Page, service: str) -> None:
    page.goto(service + "/")
    expect(page.locator("#rows .row").first).to_be_visible()
    page.locator("#submit").click()
    new = page.get_by_role("tab", name="New document", exact=True)
    load = page.get_by_role("tab", name="Load document", exact=True)
    new.focus()
    new.press("ArrowRight")
    expect(load).to_be_focused()
    expect(load).to_have_attribute("aria-selected", "true")
    expect(page.locator("#document")).to_be_visible()
    load.press("ArrowLeft")
    expect(new).to_be_focused()
    expect(new).to_have_attribute("aria-selected", "true")
    new.press("End")
    expect(load).to_be_focused()
    expect(load).to_have_attribute("aria-selected", "true")
    load.press("Home")
    expect(new).to_be_focused()
    expect(new).to_have_attribute("aria-selected", "true")
    expect(page.locator("#root")).to_be_visible()
