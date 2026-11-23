"""Source changes replace a draft only after success, with a captured snapshot."""

from __future__ import annotations

from urllib.parse import urlencode

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


def add_note(page: Page, text: str) -> None:
    row = page.locator('.row[data-path="docs"]')
    row.focus()
    page.locator("#row-note").click()
    page.locator("#note-text").fill(text)
    page.locator("#note-text").press("Enter")
    expect(row.locator(".note")).to_have_text(f"# {text}")


@pytest.mark.parametrize("width", [390, 1280])
def test_return_from_chooser_preserves_curation_and_source(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    add_note(page, "keep current work")
    original = page.locator("#region").text_content()
    address = page.url
    page.locator("#browse-source").click()
    page.locator('.source-row[data-path="src"]').click()
    page.locator("#entry-return").click()
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
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    add_note(page, "existing work")
    original = page.locator("#region").text_content()
    address = page.url
    page.route(
        "**/api/preview",
        lambda route: route.fulfill(
            status=422,
            json={
                "error": {"code": "curation", "message": "Malformed treestamp markers."}
            },
        ),
    )
    page.locator("#browse-source").click()
    page.locator('.source-row[data-path="README.md"]').click()
    page.locator("#reload").click()
    expect(page.locator("#reload-error")).to_contain_text("Malformed")
    expect(page.locator("#reload-settings")).to_be_visible()
    expect(page.locator("#reload")).to_be_enabled()
    expect(page.locator("#region")).to_have_text(original)
    assert page.url == address
    page.locator("#entry-return").click()
    add_note(page, "work after failed open")


@pytest.mark.parametrize("root", ["src", "./src", "./src/"])
def test_explicit_new_root_is_repository_relative_and_initial_depth_is_one(
    page: Page, service: str, root: str
) -> None:
    query = urlencode({"root": root, "document": ""})
    with page.expect_response("**/api/preview*") as response:
        page.goto(f"{service}/fixture/repo?{query}")
    assert response.value.ok
    data = response.value.json()
    assert data["loaded"] is False
    assert data["root"] == "src"
    assert data["document"] == ""
    expect(page.locator("#rows .row")).to_have_count(3)
    expect(page.locator("#region")).to_contain_text('root = "src"')
    expect(page.locator("#loaded-note")).to_be_hidden()
    address = page.url
    page.reload()
    expect(page.locator("#rows .row")).to_have_count(3)
    assert page.url == address


def test_successful_reopen_discards_unwritten_notes_hiding_and_folds(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    original = page.locator("#region").text_content()
    add_note(page, "discard this")
    page.locator('.row[data-path="docs"] .fold').click()
    page.locator('.row[data-path="scripts"]').focus()
    page.locator("#row-visibility").click()
    page.locator("#browse-source").click()
    page.locator('.source-row[data-path="README.md"]').click()
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
    page.goto(f"{service}/fixture/repo?root=.")
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


@pytest.mark.parametrize(
    "path,kind,field",
    [
        ({"git_bytes": "646f63ff2e6d64"}, "file", "document"),
        (" src ", "dir", "root"),
        (" README.md ", "file", "document"),
    ],
)
def test_visual_selection_retains_exact_source_identity(
    page: Page, service: str, path, kind: str, field: str
) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.route(
        "**/api/browse*",
        lambda route: route.fulfill(
            json={
                "repository": {"owner": "fixture", "name": "repo"},
                "entries": [
                    {"path": ".", "parent": None, "name": ".", "kind": "dir"},
                    {"path": path, "parent": ".", "name": path, "kind": kind},
                ],
            }
        ),
    )
    page.route(
        "**/api/preview",
        lambda route: route.fulfill(
            status=404, json={"error": {"message": "Exact path not found."}}
        ),
    )
    page.locator("#browse-source").click()
    page.locator(".source-row").nth(1).click()
    with page.expect_request("**/api/preview") as request:
        page.locator("#reload").click()
    assert request.value.post_data_json[field] == path
    expect(page.locator("#reload-error")).to_contain_text("Exact path not found.")


@pytest.mark.parametrize("width", [390, 1280])
def test_selected_entry_determines_creation_or_opening(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#reload")).to_have_text("Create")
    page.locator('.source-row[data-path="README.md"]').click()
    expect(page.locator("#reload")).to_have_text("Load")
    page.locator('.source-row[data-path="src"]').click()
    expect(page.locator("#reload")).to_have_text("Create")
    page.locator('.source-row[data-path="README.md"]').click()
    with page.expect_request("**/api/preview") as request:
        page.locator("#reload").click()
    assert request.value.post_data_json == {
        "url": "fixture/repo",
        "document": "README.md",
    }
    expect(page.locator("#reload-settings")).to_be_hidden()
    expect(page.locator("#stage-status")).to_have_text("Treestamp is up to date")
