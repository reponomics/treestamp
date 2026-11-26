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
    for selector in ("#entry-create", "#entry-browse"):
        expect(page.locator(selector)).to_be_disabled()
    repository.fill("fixture/repo")
    expect(page.locator("#entry-browse")).to_be_enabled()
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


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "invalid_link"),
        (404, "not_found"),
        (422, "curation"),
        (None, None),
    ],
)
def test_failed_direct_open_keeps_landing_input_and_accepted_draft(
    page: Page, service: str, status: int | None, code: str | None
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
    controls = page.locator("#entry-form").bounding_box()
    page.locator("#entry-create").click()
    expect(page.locator("#entry-error")).to_be_visible()
    expect(page.locator("#entry-error")).not_to_be_empty()
    # The failure takes the label's place, so the form keeps its geometry.
    assert page.locator("#entry-form").bounding_box() == controls
    expect(page.locator("#entry-welcome")).to_be_visible()
    expect(page.locator("#workspace")).to_be_hidden()
    expect(page.locator("#entry-url")).to_have_value(repository)
    for selector in ("#entry-create", "#entry-browse"):
        expect(page.locator(selector)).to_be_enabled()
    # Only an unusable address is attributed to the field, and editing clears it.
    field = page.locator("#entry-url")
    if code == "invalid_link":
        expect(field).to_have_attribute("aria-invalid", "true")
        field.press("End")
        field.press_sequentially("/")
    expect(field).not_to_have_attribute("aria-invalid", "true")
    assert len(requests) == 1
    assert page.url == address
    assert page.evaluate(DRAFT) == saved
    expect(page.locator("#region")).to_have_text(region)
