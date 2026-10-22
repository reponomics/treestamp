"""Curated examples open locally and replace the previous editing session."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.browser

EXAMPLES = [
    ("reponomics-dashboard", ".", "Choose repositories and publishing options"),
    ("reponomics-dashboard-action", ".", "GitHub Action entry point"),
    ("PolicyChecks", "src", "Start the badge service"),
]


def test_mobile_examples_reveal_choices_without_replacing_work(
    page: Page, service: str
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(service + "/")
    choices = page.locator(".example-options")
    expect(choices).to_be_hidden()
    config = page.locator('.row[data-path="config.yaml"]')
    config.get_by_role("button", name="Note", exact=True).click()
    page.locator("#note-text").fill("Keep this note")
    page.locator("#note-text").press("Enter")
    expect(page.locator("#region")).to_contain_text("Keep this note")
    original_region = page.locator("#region").text_content()
    original_url = page.url
    requests: list[str] = []
    page.on("request", lambda request: requests.append(request.url))

    page.get_by_text("Show examples", exact=True).click()
    expect(choices).to_be_visible()
    page.get_by_text("Hide examples", exact=True).click()
    expect(choices).to_be_hidden()
    expect(page.locator("#region")).to_have_text(original_region)
    assert page.url == original_url
    assert requests == []

    summary = page.locator("#examples > summary")
    summary.focus()
    summary.press("Enter")
    page.locator('button[data-example="PolicyChecks"]').click()
    expect(page.locator("#url")).to_have_value("reponomics/PolicyChecks")
    expect(choices).to_be_visible()
    page.get_by_text("Hide examples", exact=True).click()
    page.set_viewport_size({"width": 1280, "height": 844})
    expect(choices).to_be_visible()
    expect(summary).to_be_hidden()
    page.set_viewport_size({"width": 390, "height": 844})
    expect(choices).to_be_hidden()
    expect(page.get_by_text("Show examples", exact=True)).to_be_visible()


@pytest.mark.parametrize("width", [390, 1280])
def test_markdown_format_keeps_the_curated_tree_editable(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(service + "/")
    config = page.locator('.row[data-path="config.yaml"]')
    workflows = page.locator('.row[data-path=".github/workflows"]')
    note = "Choose repositories and publishing options"
    expect(config.locator(".note")).to_have_text(f"# {note}")
    expect(page.get_by_label("Format", exact=True)).to_be_hidden()

    for style, connector in [("ascii", "|-- "), ("list", "- ")]:
        page.locator("#tab-stamp").click()
        page.get_by_label("Format", exact=True).select_option(style)
        expect(page.locator("#region")).not_to_contain_text("style =")
        expect(page.locator("#region")).to_contain_text(connector + ".github/")
        expect(page.locator("#region")).to_contain_text(note)
        expect(page.locator("#tab-stamp")).to_have_attribute("aria-selected", "true")

        page.locator("#tab-editor").click()
        expect(page.get_by_label("Format", exact=True)).to_be_hidden()
        expect(config.locator(".note")).to_have_text(f"# {note}")
        expect(page.locator('.row[data-path="README.md"]')).to_have_count(0)
        expect(page.locator('.row[data-path^=".github/workflows/"]')).to_have_count(0)

    workflows.locator(".fold").click()
    expect(page.locator('.row[data-path^=".github/workflows/"]')).to_have_count(7)
    expect(config.locator(".note")).to_have_text(f"# {note}")
    page.locator("#tab-stamp").click()
    expect(page.get_by_label("Format", exact=True)).to_have_value("list")


@pytest.mark.parametrize("name,root,note", EXAMPLES)
def test_example_opens_without_requests_and_replaces_pending_source(
    page: Page, service: str, name: str, root: str, note: str
) -> None:
    requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if "/api/" in request.url else None
        ),
    )
    page.goto(service + "/")
    expect(page.locator("#rows .row").first).to_be_visible()
    page.locator("#submit").click()
    page.locator("#load-tab-new").click()
    page.locator("#root").fill("pending-folder")
    page.locator("#load-tab-document").click()
    page.locator("#document").fill("PENDING.md")
    page.keyboard.press("Escape")
    page.locator(f'button[data-example="{name}"]').click()
    expect(page.locator("#url")).to_have_value(f"reponomics/{name}")
    assert f"/reponomics/{name}@" in page.url
    expect(page.locator("#root")).to_have_value(root)
    expect(page.locator("#document")).to_have_value("")
    expect(page.locator("#rows .row").first).to_be_visible()
    expect(page.locator("#region")).to_contain_text("<!-- treestamp:start -->")
    expect(page.locator("#rows")).to_contain_text(note)
    expect(page.locator("#region")).to_contain_text(note)
    expect(page.locator("#copy")).to_be_enabled()
    expect(page.locator("#stage-status")).to_be_hidden()
    expect(page.locator("#status")).to_have_text("")
    original_region = page.locator("#region").text_content()
    page.reload()
    expect(page.locator("#region")).to_have_text(original_region)
    expect(page.locator("#url")).to_have_value(f"reponomics/{name}")
    assert requests == []


def test_reselecting_an_example_restores_its_curated_notes(
    page: Page, service: str
) -> None:
    page.goto(service + "/")
    expect(page.locator("#rows .row").first).to_be_visible()
    original_region = page.locator("#region").text_content()
    row = page.locator('.row[data-path="config.yaml"]')
    row.locator('[data-action="note"]').click()
    page.locator("#note-text").fill("My custom note")
    page.locator("#note-text").press("Enter")
    expect(row.locator(".note")).to_have_text("# My custom note")
    expect(page.locator("#region")).to_contain_text("My custom note")
    workflows = page.locator('.row[data-path=".github/workflows"]')
    workflows.locator(".fold").click()
    expect(page.locator('.row[data-path^=".github/workflows/"]')).to_have_count(7)
    expect(row.locator(".note")).to_have_text("# My custom note")

    page.locator('button[data-example="reponomics-dashboard"]').click()
    expect(page.locator("#region")).to_have_text(original_region)
    expect(page.locator('.row[data-path^=".github/workflows/"]')).to_have_count(0)
    expect(row.locator(".note")).to_have_text(
        "# Choose repositories and publishing options"
    )


@pytest.mark.parametrize("endpoint", ["op", "preview"])
def test_example_replaces_pending_requests_and_queued_edits(
    page: Page, service: str, endpoint: str
) -> None:
    with page.expect_response("**/api/preview*") as opening:
        page.goto(f"{service}/fixture/repo")
    old_response = opening.value.json()
    expect(page.locator("#rows .row")).to_have_count(9)
    # Ignore abort signals deliberately: even an already-arriving response must
    # not overwrite the newly selected example, and queued edits must be dropped.
    delay_script = """
        const originalFetch = window.fetch;
        window.delayedCalls = 0;
        window.fetch = (url, init) => {
            if (!url.startsWith('/api/ENDPOINT')) return originalFetch(url, init);
            window.delayedCalls += 1;
            return new Promise(resolve => { window.releaseResponse = resolve; });
        };
    """.replace("ENDPOINT", endpoint)
    if endpoint == "op":
        page.evaluate("() => {" + delay_script + "}")
        page.locator("#tab-stamp").click()
        page.locator("#style").select_option("ascii")
        page.locator("#style").select_option("unicode")
    else:
        # A pending initial load can be superseded by an example. Explicit
        # Load/Reload confirmations remain modal until their request settles.
        page.add_init_script(delay_script)
        page.goto(f"{service}/fixture/repo")
    page.wait_for_function("() => window.delayedCalls === 1")

    page.locator('button[data-example="PolicyChecks"]').click()
    expect(page.locator("#url")).to_have_value("reponomics/PolicyChecks")
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
    expect(page.locator("#submit")).to_be_enabled()
    expect(page.locator("#reload")).to_be_enabled()
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")


def test_old_permalink_failure_does_not_reopen_after_selecting_example(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#rows .row")).to_have_count(9)
    assert "#s=" in page.url
    page.add_init_script("""
        const originalFetch = window.fetch;
        window.unexpectedPreviews = 0;
        window.fetch = (url, init) => {
            if (url === '/api/op') {
                return new Promise(resolve => { window.releaseResponse = resolve; });
            }
            if (url.startsWith('/api/preview')) window.unexpectedPreviews += 1;
            return originalFetch(url, init);
        };
    """)
    page.reload()
    page.wait_for_function("() => Boolean(window.releaseResponse)")
    page.locator('button[data-example="PolicyChecks"]').click()
    original_region = page.locator("#region").text_content()
    page.evaluate("""async () => {
        window.releaseResponse(new Response('{}', {status: 503}));
        await new Promise(requestAnimationFrame);
    }""")
    expect(page.locator("#url")).to_have_value("reponomics/PolicyChecks")
    assert page.locator("#region").text_content() == original_region
    assert page.evaluate("window.unexpectedPreviews") == 0
