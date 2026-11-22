"""Reset restores the source tree without turning storage into a user concept."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


def annotate(page: Page) -> None:
    page.locator('.row[data-path="src"] [data-action="note"]').click()
    page.locator("#note-text").fill("A temporary note")
    page.locator("#note-save").click()
    expect(page.locator("#region")).to_contain_text("A temporary note")


def test_reset_cancel_preserves_edits_and_reset_survives_a_return(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    original = page.locator("#region").text_content()
    annotate(page)
    edited = page.locator("#region").text_content()
    address = page.url
    page.locator("#reset-tree").click()
    expect(page.locator("#reset-dialog")).to_be_visible()
    page.locator("#reset-cancel").click()
    expect(page.locator("#region")).to_have_text(edited)
    assert page.url == address
    page.locator("#reset-tree").click()
    page.locator("#reset-confirm").click()
    expect(page.locator("#reset-dialog")).to_be_hidden()
    expect(page.locator("#region")).to_have_text(original)
    page.goto(service + "/")
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#region")).to_have_text(original)


def test_failed_reset_keeps_accepted_changes(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    annotate(page)
    edited = page.locator("#region").text_content()
    address = page.url
    record = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    page.route(
        "**/api/preview*",
        lambda route: route.fulfill(
            status=503,
            json={"error": {"message": "Repository unavailable."}},
        ),
    )
    page.locator("#reset-tree").click()
    page.locator("#reset-confirm").click()
    expect(page.locator("#reset-dialog")).to_contain_text("Repository unavailable")
    expect(page.locator("#region")).to_have_text(edited)
    assert page.url == address
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == record
    page.locator("#reset-cancel").click()
    expect(page.locator("#workspace")).to_be_visible()


def test_reset_loaded_document_uses_its_captured_commit_and_source(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo?document=README.md")
    expect(page.locator("#rows .row")).to_have_count(9)
    original = page.locator("#region").text_content()
    commit = page.locator("[data-repo-commit]").first.text_content()
    annotate(page)
    page.locator("#reset-tree").click()
    with page.expect_request("**/api/preview") as request:
        page.locator("#reset-confirm").click()
    body = request.value.post_data_json
    assert body["ref"] == commit
    assert body["document"] == "README.md"
    expect(page.locator("#reset-dialog")).to_be_hidden()
    expect(page.locator("#region")).to_have_text(original)


def test_example_reset_stays_local_and_keeps_its_curated_content(
    page: Page, service: str
) -> None:
    page.goto(service + "/")
    page.locator("#explore-example").click()
    expect(page.locator("#workspace")).to_be_visible()
    original = page.locator("#region").text_content()
    requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if "/api/" in request.url else None
        ),
    )
    page.locator("#reset-tree").click()
    page.locator("#reset-confirm").click()
    expect(page.locator("#reset-dialog")).to_be_hidden()
    expect(page.locator("#region")).to_have_text(original)
    expect(page.locator("#example-context")).to_be_visible()
    assert requests == []


def test_edited_example_can_reset_after_reloading_the_page(
    page: Page, service: str
) -> None:
    page.goto(service + "/")
    page.locator("#explore-example").click()
    original = page.locator("#region").text_content()
    row = page.locator('.row[data-path="config.yaml"]')
    row.locator('[data-action="note"]').click()
    page.locator("#note-text").fill("My own configuration note")
    page.locator("#note-save").click()
    expect(row.locator(".note")).to_have_text("# My own configuration note")
    page.reload()
    expect(row.locator(".note")).to_have_text("# My own configuration note")
    requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if "/api/" in request.url else None
        ),
    )
    page.locator("#reset-tree").click()
    page.locator("#reset-confirm").click()
    expect(page.locator("#reset-dialog")).to_be_hidden()
    expect(page.locator("#region")).to_have_text(original)
    expect(page.locator("#example-context")).to_be_visible()
    assert requests == []
