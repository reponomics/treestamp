"""Root shortcuts prepare one candidate without making a provisional draft."""

from __future__ import annotations

from uuid import uuid4

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, Request, Route, expect  # noqa: E402

pytestmark = pytest.mark.browser
DRAFT = "localStorage.getItem('treestamp.current-draft')"


def record_api_requests(page: Page) -> list[Request]:
    requests: list[Request] = []
    page.on(
        "request",
        lambda request: requests.append(request) if "/api/" in request.url else None,
    )
    return requests


@pytest.mark.parametrize("activation", ["button", "enter"])
def test_direct_create_opens_fresh_root_without_loading_readme(
    page: Page, service: str, activation: str
) -> None:
    page.goto(service + "/")
    requests = record_api_requests(page)
    repository = page.locator("#entry-url")
    for selector in ("#entry-create", "#entry-load"):
        expect(page.locator(selector)).to_be_disabled()
    repository.fill("fixture/repo")
    expect(page.locator("#entry-load")).to_be_enabled()
    with page.expect_response("**/api/preview") as response:
        if activation == "enter":
            repository.press("Enter")
        else:
            page.locator("#entry-create").click()
    expect(page.locator("#workspace")).to_be_visible()
    assert len(requests) == 1
    assert requests[0].post_data_json == {
        "url": "fixture/repo",
        "root": ".",
        "document": "",
    }
    prepared = response.value.json()
    assert prepared["loaded"] is False
    assert prepared["document"] == ""
    assert prepared["root"] == "."
    # The saved README hides itself; a new root retains it as an ordinary file.
    expect(page.locator('#rows .row[data-path="README.md"]')).to_be_visible()
    expect(page.locator("#entry")).to_be_hidden()


def test_direct_readme_load_stays_on_landing_until_single_candidate_is_ready(
    page: Page, service: str
) -> None:
    page.goto(service + "/")
    requests = record_api_requests(page)
    pending: list[Route] = []
    page.route("**/api/preview", lambda route: pending.append(route))
    page.locator("#entry-url").fill("fixture/repo")
    page.locator("#entry-load").click()
    expect(page.locator("#entry-load")).to_be_disabled()
    expect(page.locator("#entry-create")).to_be_disabled()
    expect(page.locator("#entry-browse")).to_be_disabled()
    expect(page.locator("#entry-welcome")).to_be_visible()
    expect(page.locator("#workspace")).to_be_hidden()
    expect(page.locator("#entry-url")).to_have_value("fixture/repo")
    assert page.evaluate(DRAFT) is None
    assert page.url == service + "/"
    assert len(pending) == len(requests) == 1
    assert pending[0].request.post_data_json == {
        "url": "fixture/repo",
        "document": "README.md",
    }
    pending[0].continue_()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#entry")).to_be_hidden()
    expect(page.locator("#tree-document")).to_have_text("README.md")
    expect(page.locator('#rows .row[data-path="README.md"]')).to_have_count(0)
    assert len(requests) == 1
    assert page.evaluate(DRAFT) is not None


@pytest.mark.parametrize(
    ("action", "status", "code"),
    [
        ("load", 404, "not_found"),
        ("load", 422, "document_has_no_treestamp"),
        ("load", 422, "curation"),
        ("load", None, None),
        ("create", None, None),
    ],
)
def test_failed_direct_open_keeps_landing_input_and_accepted_draft(
    page: Page, service: str, action: str, status: int | None, code: str | None
) -> None:
    page.goto(service + "/")
    page.locator("#explore-example").click()
    expect(page.locator("#workspace")).to_be_visible()
    saved = page.evaluate(DRAFT)
    address = page.url
    region = page.locator("#region").text_content()
    page.locator(".wordmark").click()
    requests = record_api_requests(page)
    message = f"Fixture failure {uuid4()}"

    def reject(route: Route) -> None:
        if status is None:
            route.abort()
        else:
            route.fulfill(
                status=status, json={"error": {"code": code, "message": message}}
            )

    page.route("**/api/preview", reject)
    repository = "fixture/repo"
    page.locator("#entry-url").fill(repository)
    page.locator(f"#entry-{action}").click()
    expect(page.locator("#entry-error")).to_be_visible()
    if status is not None:
        expect(page.locator("#entry-error")).to_contain_text(message)
    expect(page.locator("#entry-welcome")).to_be_visible()
    expect(page.locator("#workspace")).to_be_hidden()
    expect(page.locator("#entry-url")).to_have_value(repository)
    for selector in ("#entry-create", "#entry-load", "#entry-browse"):
        expect(page.locator(selector)).to_be_enabled()
    assert len(requests) == 1
    assert page.url == address
    assert page.evaluate(DRAFT) == saved
    expect(page.locator("#region")).to_have_text(region)
