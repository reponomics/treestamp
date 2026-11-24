"""The opt-in example and retained captured example links stay offline."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser

EXAMPLES = [("treestamp", ".", "Package metadata and dependencies")]


def explore_from_editor(page: Page) -> None:
    page.locator(".wordmark").click()
    page.locator("#explore-example").click()


@pytest.mark.parametrize("width", [390, 1280])
def test_example_is_a_direct_offline_opt_in(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if "/api/" in request.url else None
        ),
    )
    page.goto(service + "/")
    expect(page.locator("#entry-welcome")).to_be_visible()
    expect(page.locator("#workspace")).to_be_hidden()
    page.locator("#explore-example").click()
    expect(page.locator("#url")).to_have_value("reponomics/treestamp")
    expect(page.locator("#example-context")).to_have_count(0)
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#reload-settings")).to_be_hidden()
    assert requests == []


@pytest.mark.parametrize("width", [390, 1280])
def test_markdown_format_keeps_the_curated_tree_editable(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(service + "/")
    page.locator("#explore-example").click()
    config = page.locator('.row[data-path="pyproject.toml"]')
    workflows = page.locator('.row[data-path="src/treestamp"]')
    note = "Package metadata and dependencies"
    expect(config.locator(".note")).to_have_text(f"# {note}")
    expect(page.get_by_label("Format", exact=True)).to_be_hidden()

    for style, connector in [("ascii", "|-- "), ("list", "- ")]:
        page.locator("#tab-stamp").click()
        page.get_by_label("Format", exact=True).select_option(style)
        expect(page.locator("#region")).not_to_contain_text("style =")
        expect(page.locator("#region")).to_contain_text(connector + "src/")
        expect(page.locator("#region")).to_contain_text(note)
        expect(page.locator("#tab-stamp")).to_have_attribute("aria-selected", "true")

        page.locator("#tab-editor").click()
        expect(page.get_by_label("Format", exact=True)).to_be_hidden()
        expect(config.locator(".note")).to_have_text(f"# {note}")
        expect(page.locator('.row[data-path="README.md"]')).to_have_count(0)
        expect(page.locator('.row[data-path^="src/treestamp/"]')).to_have_count(0)

    workflows.locator(".fold").click()
    expect(page.locator('.row[data-path^="src/treestamp/"]')).not_to_have_count(0)
    expect(config.locator(".note")).to_have_text(f"# {note}")
    page.locator("#tab-stamp").click()
    expect(page.get_by_label("Format", exact=True)).to_have_value("list")


@pytest.mark.parametrize("name,root,note", EXAMPLES)
def test_existing_example_links_still_open_without_api_requests(
    page: Page, service: str, name: str, root: str, note: str
) -> None:
    page.goto(service + "/")
    address = page.evaluate(
        """async name => {
        const { EXAMPLES } = await import('/static/example.js');
        const { addressFor } = await import('/static/logic.js');
        const data = EXAMPLES[name];
        return addressFor(data.permalink, data.state, location.origin);
    }""",
        name,
    )
    requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if "/api/" in request.url else None
        ),
    )
    page.goto(service + address)
    expect(page.locator("#url")).to_have_value(f"reponomics/{name}")
    expect(page.locator("#root")).to_have_value(root)
    expect(page.locator("#region")).to_contain_text(note)
    original = page.locator("#region").text_content()
    page.reload()
    expect(page.locator("#region")).to_have_text(original)
    assert requests == []


def test_reselecting_example_replaces_notes_with_its_original_curation(
    page: Page, service: str
) -> None:
    page.goto(service + "/")
    page.locator("#explore-example").click()
    original = page.locator("#region").text_content()
    row = page.locator('.row[data-path="pyproject.toml"]')
    row.focus()
    page.locator("#row-note").click()
    page.locator("#note-text").fill("My custom note")
    page.locator("#note-text").press("Enter")
    expect(row.locator(".note")).to_have_text("# My custom note")
    explore_from_editor(page)
    expect(page.locator("#region")).to_have_text(original)


def test_example_replaces_queued_edits_without_accepting_late_responses(
    page: Page, service: str
) -> None:
    with page.expect_response("**/api/preview*") as opening:
        page.goto(f"{service}/fixture/repo?root=.")
    old_response = opening.value.json()
    expect(page.locator("#rows .row")).to_have_count(9)
    page.evaluate("""() => {
        const fetch = window.fetch;
        window.delayedCalls = 0;
        window.fetch = (url, init) => {
            if (url !== '/api/op') return fetch(url, init);
            window.delayedCalls++;
            return new Promise(resolve => { window.releaseResponse = resolve; });
        };
    }""")
    page.locator("#tab-stamp").click()
    page.locator("#style").select_option("ascii")
    page.locator("#style").select_option("unicode")
    page.wait_for_function("window.delayedCalls === 1")
    explore_from_editor(page)
    expect(page.locator("#url")).to_have_value("reponomics/treestamp")
    region = page.locator("#region").text_content()
    address = page.url
    page.evaluate(
        """async body => {
        window.releaseResponse(new Response(JSON.stringify(body), {status: 200}));
        await new Promise(requestAnimationFrame);
    }""",
        old_response,
    )
    assert page.locator("#region").text_content() == region
    assert page.url == address
    assert page.evaluate("window.delayedCalls") == 1
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")


def test_late_browse_failure_does_not_reopen_after_selecting_example(
    page: Page, service: str
) -> None:
    page.goto(service + "/")
    page.evaluate("""() => {
        const fetch = window.fetch;
        window.fetch = (url, init) => url.startsWith('/api/browse')
            ? new Promise(resolve => { window.releaseResponse = resolve; })
            : fetch(url, init);
    }""")
    page.locator("#entry-url").fill("fixture/repo")
    page.locator("#entry-browse").click()
    page.wait_for_function("Boolean(window.releaseResponse)")
    page.locator("#entry-change-repo").click()
    page.locator("#explore-example").click()
    original = page.locator("#region").text_content()
    page.evaluate("""async () => {
        window.releaseResponse(new Response('{}', {status: 503}));
        await new Promise(requestAnimationFrame);
    }""")
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#entry")).to_be_hidden()
    expect(page.locator("#error")).to_be_hidden()
    assert page.locator("#region").text_content() == original
