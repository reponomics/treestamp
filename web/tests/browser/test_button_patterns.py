"""Shared action patterns retain their appearance across screens and themes."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Locator, Page, expect  # noqa: E402

pytestmark = [
    pytest.mark.browser,
    pytest.mark.parametrize("scheme", ["light", "dark"]),
    pytest.mark.parametrize("width", [390, 1440]),
]

BUTTON_APPEARANCE = (
    "fontFamily",
    "fontWeight",
    "backgroundColor",
    "color",
    "borderTopColor",
    "borderTopStyle",
    "borderTopWidth",
    "borderTopLeftRadius",
)
WORDMARK_TYPE = ("fontFamily", "fontWeight")
FOCUS_APPEARANCE = ("outlineColor", "outlineStyle", "outlineWidth", "outlineOffset")


def appearance(
    locator: Locator, properties: tuple[str, ...] = BUTTON_APPEARANCE
) -> dict[str, str]:
    return locator.evaluate(
        """(element, properties) => {
            const style = getComputedStyle(element);
            return Object.fromEntries(properties.map(key => [key, style[key]]));
        }""",
        properties,
    )


def open_landing(page: Page, service: str, scheme: str, width: int) -> None:
    page.set_viewport_size({"width": width, "height": 900})
    page.emulate_media(color_scheme=scheme)
    page.goto(service + "/")
    page.evaluate("document.fonts.ready")
    expect(page.locator("html")).to_have_attribute("data-theme", scheme)
    page.mouse.move(0, 0)


def relative_tracking(locator: Locator) -> float:
    return locator.evaluate(
        """element => {
            const style = getComputedStyle(element);
            return parseFloat(style.letterSpacing) / parseFloat(style.fontSize);
        }"""
    )


def test_secondary_buttons_and_links_share_appearance_across_screens(
    page: Page, service: str, scheme: str, width: int
) -> None:
    open_landing(page, service, scheme, width)
    theme = page.locator("#theme-toggle")
    github = page.locator(".masthead .docs")
    secondary = appearance(theme)
    assert appearance(github) == secondary
    hero = page.locator("#entry-title")
    navbar = page.locator(".wordmark h1")
    assert appearance(hero, WORDMARK_TYPE) == appearance(navbar, WORDMARK_TYPE)
    assert relative_tracking(hero) == pytest.approx(relative_tracking(navbar))

    theme.hover()
    hovered = appearance(theme)
    assert hovered != secondary
    github.hover()
    assert appearance(github) == hovered

    # Keyboard focus is equally visible for button actions and linked actions.
    page.mouse.move(0, 0)
    theme.focus()
    theme.press("Tab")
    expect(github).to_be_focused()
    focus = appearance(github, FOCUS_APPEARANCE)
    assert github.evaluate(
        "element => parseFloat(getComputedStyle(element).outlineWidth) > 0"
    )
    github.press("Shift+Tab")
    expect(theme).to_be_focused()
    assert appearance(theme, FOCUS_APPEARANCE) == focus

    page.locator("#explore-example").click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")
    page.mouse.move(0, 0)
    for selector in ("#visit-repo", "#copy"):
        action = page.locator(selector)
        expect(action).to_be_visible()
        expect(action).to_be_enabled()
        assert appearance(action) == secondary, selector

    page.locator(".wordmark").click()
    expect(page.locator("#entry-welcome")).to_be_visible()
    page.mouse.move(0, 0)
    for selector in (
        "#entry-return-welcome",
        "#entry-load",
        "#entry-browse",
        "#explore-example",
    ):
        action = page.locator(selector)
        expect(action).to_be_visible()
        expect(action).to_be_enabled()
        assert appearance(action) == secondary, selector


def test_primary_actions_share_appearance_and_distinguish_disabled_state(
    page: Page, service: str, scheme: str, width: int
) -> None:
    open_landing(page, service, scheme, width)
    direct_create = page.locator("#entry-create")
    expect(direct_create).to_be_disabled()
    disabled = appearance(direct_create)
    page.locator("#entry-url").fill("fixture/repo")
    expect(direct_create).to_be_enabled()
    primary = appearance(direct_create)
    assert primary != disabled
    assert primary != appearance(page.locator("#explore-example"))

    page.locator("#entry-browse").click()
    create = page.locator("#source-create")
    expect(create).to_be_enabled()
    page.mouse.move(0, 0)
    assert appearance(create) == primary
    create.click()
    expect(page.locator("#workspace")).to_be_visible()
    page.locator("#row-note").click()
    apply_note = page.locator("#note-save")
    expect(apply_note).to_be_visible()
    expect(apply_note).to_be_enabled()
    page.mouse.move(0, 0)
    assert appearance(apply_note) == primary
