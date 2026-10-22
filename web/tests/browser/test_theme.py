"""Theme defaults, deliberate choices, and unavailable browser storage."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_theme_follows_system_until_user_chooses(
    page: Page, service: str, scheme: str
) -> None:
    page.emulate_media(color_scheme=scheme)
    page.goto(service + "/")
    expect(page.locator("html")).to_have_attribute("data-theme", scheme)
    other = "dark" if scheme == "light" else "light"
    page.emulate_media(color_scheme=other)
    expect(page.locator("html")).to_have_attribute("data-theme", other)


def test_theme_toggle_persists_both_choices(page: Page, service: str) -> None:
    page.emulate_media(color_scheme="light")
    page.goto(service + "/")
    toggle = page.locator("#theme-toggle")
    expect(toggle).to_have_text("Dark mode")
    toggle.click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(toggle).to_have_attribute("aria-pressed", "true")
    expect(toggle).to_have_accessible_name("Switch to light mode")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    toggle.click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    expect(toggle).to_have_attribute("aria-pressed", "false")
    page.emulate_media(color_scheme="dark")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    expect(toggle).to_have_accessible_name("Switch to dark mode")


def test_theme_works_when_storage_is_unavailable(page: Page, service: str) -> None:
    page.add_init_script(
        """Object.defineProperty(window, 'localStorage', {
          get() { throw new DOMException('Unavailable', 'SecurityError'); }
        });"""
    )
    page.emulate_media(color_scheme="light")
    page.goto(service + "/")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    page.locator("#theme-toggle").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("#theme-toggle")).to_have_text("Light mode")
