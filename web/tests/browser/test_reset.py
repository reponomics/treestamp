"""Discard restores the accepted session start without repeating preparation."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


def annotate(page: Page) -> None:
    page.locator('.row[data-path="src"]').focus()
    page.locator("#row-note").click()
    page.locator("#note-text").fill("A temporary note")
    page.locator("#note-save").click()
    expect(page.locator("#region")).to_contain_text("A temporary note")


def test_discard_cancel_preserves_edits_and_reset_survives_a_return(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    original = page.locator("#region").text_content()
    annotate(page)
    edited = page.locator("#region").text_content()
    address = page.url
    expect(page.locator("#reset-tree")).to_have_text("Discard changes")
    page.locator("#reset-tree").click()
    expect(page.locator("#reset-dialog")).to_be_visible()
    expect(page.locator("#reset-title")).to_have_text("Discard changes?")
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


def test_failed_discard_keeps_accepted_changes(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    annotate(page)
    edited = page.locator("#region").text_content()
    address = page.url
    record = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    page.route(
        "**/api/op",
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


def test_discard_loaded_document_uses_its_captured_commit_and_source(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo?document=README.md")
    expect(page.locator("#rows .row")).to_have_count(9)
    original = page.locator("#region").text_content()
    commit = page.locator("[data-repo-commit]").first.text_content()
    annotate(page)
    page.locator("#reset-tree").click()
    with page.expect_request("**/api/op") as request:
        page.locator("#reset-confirm").click()
    body = request.value.post_data_json
    assert body["ref"] == commit
    assert body["document"] == "README.md"
    assert body["op"]["type"] == "reset"
    expect(page.locator("#reset-dialog")).to_be_hidden()
    expect(page.locator("#region")).to_have_text(original)


def test_example_discard_stays_local_and_keeps_its_curated_content(
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
    expect(page.locator("#example-context")).to_have_count(0)
    expect(page.locator("#active-repository")).to_contain_text("reponomics/")
    assert requests == []


def test_edited_example_can_discard_after_reloading_the_page(
    page: Page, service: str
) -> None:
    page.goto(service + "/")
    page.locator("#explore-example").click()
    original = page.locator("#region").text_content()
    row = page.locator('.row[data-path="config.yaml"]')
    row.focus()
    page.locator("#row-note").click()
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
    expect(page.locator("#example-context")).to_have_count(0)
    expect(page.locator("#active-repository")).to_contain_text("reponomics/")
    assert requests == []
