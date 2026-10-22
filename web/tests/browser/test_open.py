"""Late Open results belong only to the session that requested them."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


def test_updated_open_shows_compact_completion_without_a_confirmation(
    page: Page, service: str
) -> None:
    def change_notice(route):
        response = route.fetch()
        data = response.json()
        data["dirty"] = True
        data["notice"] = "Treestamp updated"
        route.fulfill(response=response, json=data)

    page.route("**/api/preview*", change_notice)
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#notice")).to_be_hidden()
    expect(page.locator("#stage-status")).to_have_text("Treestamp updated")
    expect(page.locator("#notice-undo")).to_be_hidden()
    expect(page.locator("#status")).to_have_text("")
    expect(page.locator("dialog[open]")).to_have_count(0)


def test_unchanged_open_has_no_update_notice(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#notice")).to_be_hidden()
    expect(page.locator("#stage-status")).to_have_text("Treestamp is up to date")
    expect(page.locator("#status")).to_have_text("")


def test_unavailable_captured_source_never_falls_back_to_latest_head(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    address = page.url
    previews: list[str] = []
    page.on(
        "request",
        lambda request: (
            previews.append(request.url) if "/api/preview" in request.url else None
        ),
    )
    page.route(
        "**/api/op",
        lambda route: route.fulfill(
            status=404, json={"error": {"message": "Captured snapshot unavailable."}}
        ),
    )
    page.reload()
    expect(page.locator("#error")).to_contain_text("Captured snapshot unavailable.")
    expect(page.locator("#stage-status")).to_have_text("No tree")
    assert page.url == address
    assert previews == []


def test_invalid_fragment_is_reported_without_creating_another_draft(
    page: Page, service: str
) -> None:
    requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if "/api/" in request.url else None
        ),
    )
    page.goto(f"{service}/fixture/repo#s=invalid!")
    expect(page.locator("#error")).to_contain_text("invalid editing state")
    assert requests == []


def test_byte_named_row_undo_preserves_identity_after_hiding(
    page: Page, service: str
) -> None:
    """Exercise transport with synthetic byte facts, independent of host filenames."""
    data: dict = {}
    identity = {"git_bytes": "7372632fff"}
    retained_row: dict = {}
    operations: list[dict] = []

    def load(route):
        nonlocal data, retained_row
        response = route.fetch()
        data = response.json()
        retained_row = next(row for row in data["rows"] if row["path"] == "src/util.py")
        retained_row.update(path=identity, name="\\xff")
        route.fulfill(response=response, json=data)

    def operate(route):
        operation = route.request.post_data_json["op"]
        operations.append(operation)
        if operation["type"] == "hide":
            data["rows"].remove(retained_row)
            data["state"]["curation"]["hidden"].append(identity)
        else:
            data["rows"].append(retained_row)
            data["state"]["curation"]["hidden"].remove(identity)
        data["state"]["revision"] += 1
        route.fulfill(json=data)

    page.route("**/api/preview*", load)
    page.route("**/api/op", operate)
    page.goto(f"{service}/fixture/repo")
    row = page.locator('.row[data-path="/git/7372632fff"]')
    expect(row).to_be_visible()
    row.get_by_role("button", name="Hide", exact=True).click()
    expect(row).to_have_count(0)
    page.locator("#notice-undo").click()
    expect(row).to_be_visible()
    assert [operation["type"] for operation in operations] == ["hide", "unhide"]
    assert all(operation["path"] == identity for operation in operations)
