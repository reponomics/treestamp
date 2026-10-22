"""Project information stays accessible without disturbing the editing session."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, Route, expect  # noqa: E402

pytestmark = pytest.mark.browser


def test_info_preserves_curated_output_and_the_permalink(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    row = page.locator('.row[data-path="src"]')
    row.locator('[data-action="note"]').click()
    page.locator("#note-text").fill("Keep this annotation")
    page.locator("#note-text").press("Enter")
    expect(page.locator("#region")).to_contain_text("Keep this annotation")
    original_output = page.locator("#region").text_content()
    original_url = page.url
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))

    page.get_by_role("tab", name="Info", exact=True).click()
    panel = page.get_by_role("tabpanel", name="Info", exact=True)
    expect(panel).to_be_visible()
    expect(panel.get_by_role("heading", level=2)).to_have_text(
        ["About treestamp", "Usage guide", "Privacy notice", "Contributing"]
    )
    expect(page.locator("#copy")).to_be_hidden()
    expect(page.locator("#copy-status")).to_be_hidden()
    expect(page.locator(".settings-open")).to_be_hidden()
    page.keyboard.press("Tab")
    expect(page.get_by_role("region", name="Project information")).to_be_focused()

    page.get_by_role("tab", name="Markdown", exact=True).click()
    expect(page.locator("#region")).to_have_text(original_output)
    expect(page.locator("#copy")).to_be_visible()
    page.get_by_role("tab", name="Tree", exact=True).click()
    expect(row.locator(".note")).to_have_text("# Keep this annotation")
    assert page.url == original_url
    assert requests == []


@pytest.mark.parametrize("failed", [False, True])
def test_info_stays_selected_through_an_initial_repository_load(
    page: Page, service: str, failed: bool
) -> None:
    pending: list[Route] = []
    page.route("**/api/preview*", lambda route: pending.append(route))
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "true")
    expect(page.locator("#submit")).to_be_disabled()
    page.get_by_role("tab", name="Info", exact=True).click()
    expect(page.locator("#info-panel")).to_be_visible()
    expect(page.locator("#stage-status")).to_be_hidden()
    assert len(pending) == 1
    if failed:
        pending[0].fulfill(
            status=503, json={"error": {"message": "Repository unavailable."}}
        )
        expect(page.locator("#error")).to_contain_text("Repository unavailable.")
    else:
        pending[0].continue_()
        expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#submit")).to_be_enabled()
    expect(page.locator("#tab-info")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#info-panel")).to_be_visible()
    expect(page.locator("#editor-panel")).to_be_hidden()
    expect(page.locator("#stage-status")).to_be_hidden()
    expect(page.locator("#copy")).to_be_hidden()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize(("width", "height"), [(320, 844), (1280, 420)])
def test_info_fits_and_all_sections_are_reachable(
    page: Page, service: str, scheme: str, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.emulate_media(color_scheme=scheme)
    page.route("**/api/**", lambda route: route.abort())
    page.goto(service + "/")
    page.get_by_role("tab", name="Info", exact=True).click()
    page.evaluate("document.fonts.ready")
    expect(page.locator("html")).to_have_attribute("data-theme", scheme)
    expect(page.locator("#error")).to_be_hidden()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

    sheet = page.get_by_role("region", name="Project information")
    last_heading = sheet.get_by_role("heading", name="Contributing", exact=True)
    assert sheet.evaluate("element => element.scrollWidth <= element.clientWidth")
    if width >= 1024:
        assert page.evaluate(
            "document.documentElement.scrollHeight <= window.innerHeight"
        )
        assert sheet.evaluate("element => element.scrollHeight > element.clientHeight")
        sheet.focus()
        sheet.press("End")
        expect(last_heading).to_be_in_viewport(ratio=1)
        expect(page.get_by_role("tablist", name="View")).to_be_in_viewport(ratio=1)
    else:
        last_heading.scroll_into_view_if_needed()
        expect(last_heading).to_be_in_viewport(ratio=1)
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )


def test_info_has_release_guidance_and_reporting_links(
    page: Page, service: str
) -> None:
    page.goto(service + "/")
    page.get_by_role("tab", name="Info", exact=True).click()
    info = page.locator("#info-panel")
    expect(info).not_to_contain_text("will appear here")
    expect(info).to_contain_text("frozen snapshot")
    expect(info).to_contain_text("Repository data is cached temporarily")
    expect(info).to_contain_text("visitors' GitHub account information is not accessed")
    expect(info.get_by_role("link", name="GitHub", exact=True)).to_have_attribute(
        "href", "https://github.com/reponomics/treestamp"
    )
    expect(
        info.get_by_role("link", name="private vulnerability reporting")
    ).to_have_attribute(
        "href", "https://github.com/reponomics/treestamp/security/advisories/new"
    )
    expect(info.get_by_role("link", name="conduct@reponomics.org")).to_have_attribute(
        "href", "mailto:conduct@reponomics.org"
    )
