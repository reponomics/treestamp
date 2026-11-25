"""The landing page keeps its next actions reachable across window sizes."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize(
    ("width", "height"),
    # A 305px viewport also exercises the width lost to a 15px desktop scrollbar.
    [(305, 568), (320, 568), (390, 667), (768, 1024), (1440, 900)],
)
def test_landing_actions_are_reachable_and_keyboard_browsing_returns_to_welcome(
    page: Page, service: str, scheme: str, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.emulate_media(color_scheme=scheme)
    page.goto(service + "/")
    page.evaluate("document.fonts.ready")
    expect(page.locator("html")).to_have_attribute("data-theme", scheme)

    welcome = page.locator("#entry-welcome")
    hero = welcome.get_by_role("heading")
    repository = page.locator("#entry-url")
    create = page.locator("#entry-create")
    load = page.locator("#entry-load")
    browse = page.locator("#entry-browse")
    example = page.locator("#explore-example")
    expect(hero).to_be_visible()
    expect(repository).to_be_focused()
    for control in (repository, create, load, browse, example):
        expect(control).to_be_in_viewport(ratio=1)
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    for container in (page.locator("#entry"), welcome):
        assert container.evaluate("node => node.scrollWidth <= node.clientWidth")

    # The illustration must not add a keyboard stop between input and action.
    repository.fill("fixture/repo")
    repository.press("Tab")
    expect(create).to_be_focused()
    create.press("Tab")
    expect(load).to_be_focused()
    load.press("Tab")
    expect(browse).to_be_focused()
    browse.press("Enter")
    expect(page.locator("#source-create")).to_be_enabled()
    expect(welcome).to_be_hidden()
    expect(page.locator("#reload-settings")).to_be_visible()

    page.locator("#entry-change-repo").click()
    expect(welcome).to_be_visible()
    expect(hero).to_be_visible()
    expect(repository).to_have_value("fixture/repo")
    expect(repository).to_be_focused()
    expect(page.locator("#reload-settings")).to_be_hidden()
    expect(page.locator("#workspace")).to_be_hidden()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 1280])
def test_landing_branches_join_adjacent_rows_and_end_at_the_last_name(
    page: Page, service: str, scheme: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(color_scheme=scheme)
    page.goto(service + "/")
    page.locator(".sample-tree .indent.branch").first.wait_for()
    page.evaluate("document.fonts.ready")
    rows = page.locator(".sample-row").evaluate_all(
        "elements => elements.map(element => element.getBoundingClientRect().toJSON())"
    )
    for previous, following in zip(rows, rows[1:], strict=False):
        assert previous["bottom"] == pytest.approx(following["top"])
    for branch in page.locator(
        ".sample-tree .indent.trunk, .sample-tree .indent.branch"
    ).all():
        stroke = branch.evaluate(
            """element => {
                const vertical = getComputedStyle(element, '::before');
                const arm = getComputedStyle(element, '::after');
                const bounds = element.getBoundingClientRect();
                return {
                    height: bounds.height,
                    top: parseFloat(vertical.top),
                    bottom: parseFloat(vertical.bottom),
                    arm: parseFloat(arm.top),
                    last: element.classList.contains('last'),
                    width: parseFloat(vertical.borderLeftWidth),
                };
            }"""
        )
        assert stroke["width"] > 0
        assert stroke["top"] == 0
        if stroke["last"]:
            assert stroke["bottom"] == pytest.approx(stroke["height"] / 2)
            assert stroke["arm"] == pytest.approx(stroke["height"] / 2)
        else:
            assert stroke["bottom"] == 0
    assert page.locator(".sample-tree").evaluate(
        "element => element.scrollWidth <= element.clientWidth"
    )
