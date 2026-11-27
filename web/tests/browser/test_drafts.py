"""Returning visitors choose whether to resume their accepted local draft."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

from .test_open import decode_state, encode_state  # noqa: E402

pytestmark = pytest.mark.browser


def curate(page: Page, service: str) -> str:
    page.goto(f"{service}/fixture/repo?root=.")
    row = page.locator('.row[data-path="docs"]')
    row.focus()
    page.locator("#row-note").click()
    page.locator("#note-text").fill("Remember this work")
    page.locator("#note-text").press("Enter")
    expect(row.locator(".note")).to_have_text("# Remember this work")
    page.locator('.row[data-path="scripts"]').focus()
    page.locator("#row-visibility").click()
    expect(page.locator('.row[data-path="scripts"]')).to_have_count(0)
    return page.locator("#region").text_content() or ""


@pytest.mark.parametrize("destination", ["/", "/fixture/repo"])
def test_return_restores_notes_hides_and_can_resume_from_picker(
    page: Page, service: str, destination: str
) -> None:
    original = curate(page, service)
    page.goto("about:blank")
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    page.goto(service + destination)
    expect(page.locator("#workspace")).to_be_hidden()
    assert not any("/api/op" in url or "/api/preview" in url for url in requests)
    assert page.url == service + destination
    if destination != "/":
        page.locator("#entry-change-repo").click()
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#region")).to_have_text(original)
    expect(page.locator("#draft-status, #forget-draft")).to_have_count(0)
    expect(page.locator('.row[data-path="scripts"]')).to_have_count(0)
    page.locator(".wordmark").click()
    page.locator("#entry-url").fill("fixture/repo")
    page.locator("#entry-browse").click()
    expect(page.locator("#replace-draft-warning")).to_have_count(0)
    page.locator("#entry-change-repo").click()
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#region")).to_have_text(original)


def test_opening_another_repository_replaces_the_one_saved_draft(
    page: Page, service: str
) -> None:
    curate(page, service)
    page.goto(f"{service}/fixture/another?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#url")).to_have_value("fixture/another")
    expect(page.locator("#region")).not_to_contain_text("Remember this work")
    page.goto(service + "/")
    expect(page.locator("#workspace")).to_be_hidden()
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#url")).to_have_value("fixture/another")
    expect(page.locator("#draft-status, #forget-draft")).to_have_count(0)


def test_expired_draft_does_not_silently_load_head_and_can_start_fresh(
    page: Page, service: str
) -> None:
    curate(page, service)
    saved = page.evaluate("localStorage.getItem('treestamp.current-draft')")
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
    previews: list[str] = []
    page.on(
        "request",
        lambda request: (
            previews.append(request.url) if "/api/preview" in request.url else None
        ),
    )
    page.goto(service + "/")
    expect(page.locator("#entry-error")).to_be_hidden()
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#entry-error")).to_contain_text("Snapshot expired")
    assert previews == []
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == saved
    page.locator("#entry-url").fill("fixture/repo")
    page.locator("#entry-browse").click()
    page.locator("#source-create").click()
    expect(page.locator("#reload-settings")).to_be_hidden()
    expect(page.locator("#rows .row")).not_to_have_count(0)


def test_failed_edit_keeps_the_last_accepted_local_draft(
    page: Page, service: str
) -> None:
    original = curate(page, service)
    saved = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    page.route(
        "**/api/op",
        lambda route: route.fulfill(
            status=503, json={"error": {"message": "Try later"}}
        ),
    )
    page.locator('.row[data-path="docs"]').focus()
    page.locator("#row-visibility").click()
    expect(page.locator("#error")).to_contain_text("Try later")
    expect(page.locator("#region")).to_have_text(original)
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == saved


def test_clearing_site_data_returns_to_welcome(page: Page, service: str) -> None:
    curate(page, service)
    page.evaluate("localStorage.clear()")
    page.goto(service + "/")
    expect(page.locator("#entry-welcome")).to_be_visible()
    expect(page.locator("#workspace")).to_be_hidden()
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") is None


def test_storage_failure_does_not_prevent_editing(page: Page, service: str) -> None:
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', {get() {throw new Error('blocked')}})"
    )
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#error")).to_be_hidden()
    expect(page.locator("#draft-status, #forget-draft")).to_have_count(0)
    page.locator('.row[data-path="scripts"]').focus()
    page.locator("#row-visibility").click()
    expect(page.locator('.row[data-path="scripts"]')).to_have_count(0)
    expect(page.locator("#copy")).to_be_enabled()


def test_failed_network_restore_can_be_replaced_by_a_fresh_load(
    page: Page, service: str
) -> None:
    curate(page, service)
    page.route("**/api/op", lambda route: route.abort())
    page.goto(service + "/")
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#entry-error")).to_contain_text("Could not reach the service")
    page.locator("#entry-url").fill("fixture/repo")
    page.locator("#entry-browse").click()
    page.locator("#source-create").click()
    expect(page.locator("#reload-settings")).to_be_hidden()
    expect(page.locator("#rows .row")).not_to_have_count(0)


def test_draft_whose_settings_cannot_be_displayed_is_never_offered(
    page: Page, service: str
) -> None:
    # Regression: such a draft was offered, and resuming it threw.
    curate(page, service)
    record = json.loads(
        page.evaluate("localStorage.getItem('treestamp.current-draft')")
    )
    address, _, fragment = record["address"].partition("#s=")
    state = decode_state(fragment)
    state["curation"]["settings"]["root"] = None
    record["address"] = f"{address}#s={encode_state(state)}"
    page.evaluate(
        "value => localStorage.setItem('treestamp.current-draft', value)",
        json.dumps(record),
    )
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(service + "/")
    expect(page.locator("#entry")).to_be_visible()
    expect(page.locator("#entry-return-welcome")).to_be_hidden()
    assert errors == []
