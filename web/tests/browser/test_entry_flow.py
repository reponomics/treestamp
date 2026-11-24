"""Choosing a known repository provides context before the editor opens."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, Route, expect  # noqa: E402

pytestmark = pytest.mark.browser
MIN_VISIBLE_PICKER_ROWS = 5


def choose(page: Page, path: str) -> None:
    page.locator("#source-browser").locator(f'[data-path="{path}"]').click()


@pytest.mark.parametrize("width", [390, 1280])
def test_first_visit_waits_for_intent_and_browsing_does_not_create_a_draft(
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
    expect(page.locator("#entry-title")).to_be_visible()
    expect(page.locator("#workspace")).to_be_hidden()
    expect(page.locator("dialog[open]")).to_have_count(0)
    assert requests == []
    page.get_by_label("Public GitHub repository").fill("fixture/repo")
    page.locator("#entry-browse").click()
    choose(page, "src")
    expect(page.locator('.source-row[data-path="src"]')).to_have_attribute(
        "aria-selected", "true"
    )
    assert all("/api/browse?" in url for url in requests)
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") is None
    page.locator("#source-create").click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#rows .row")).to_have_count(3)
    expect(page.locator("#region")).to_contain_text('root = "src"')
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_example_offramp_opens_one_curated_editor_without_requests(
    page: Page, service: str
) -> None:
    requests: list[str] = []
    page.on(
        "request",
        lambda request: (
            requests.append(request.url) if "/api/" in request.url else None
        ),
    )
    page.goto(service + "/")
    expect(page.get_by_role("button", name="Try example", exact=True)).to_have_count(1)
    page.get_by_role("button", name="Try example", exact=True).click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#entry")).to_be_hidden()
    expect(page.locator("#example-context")).to_have_count(0)
    expect(page.locator("#active-repository")).to_have_text("reponomics/treestamp")
    expect(page.locator(".canvas-caption")).to_be_hidden()
    expect(page.locator("#rows")).to_contain_text("Package metadata and dependencies")
    assert requests == []


def test_bare_repository_starts_in_tree_chooser(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo")
    expect(page.locator("#reload-settings")).to_be_visible()
    expect(page.locator("#load-target")).to_have_text("fixture/repo")
    expect(page.locator("#workspace")).to_be_hidden()
    choose(page, "README.md")
    page.locator("#source-load").click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#tree-document")).to_have_text("README.md")


def test_plain_document_warns_without_changing_selection_or_creating_a_tree(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    page.locator('.source-row[data-path="docs"]').click()
    choose(page, "docs/guide.md")
    page.locator("#source-load").click()
    expect(page.locator("#reload-error")).to_contain_text(
        "No treestamp found in docs/guide.md"
    )
    expect(page.locator("#reload-error")).to_contain_text(
        "Choose another document to load"
    )
    selected = page.locator('#source-browser [data-path="docs/guide.md"]')
    expect(selected).to_have_attribute("aria-selected", "true")
    expect(selected).to_be_focused()
    expect(page.locator("#source-load")).to_be_enabled()
    expect(page.locator("#source-create")).to_be_disabled()
    expect(page.locator("#workspace")).to_be_hidden()
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") is None
    choose(page, "README.md")
    page.locator("#source-load").click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#tree-document")).to_have_text("README.md")


def test_malformed_document_stays_an_error_and_does_not_offer_creation(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo")
    choose(page, "README.md")
    page.route(
        "**/api/preview",
        lambda route: route.fulfill(
            status=422,
            json={
                "error": {
                    "code": "curation",
                    "message": "Incomplete treestamp markers.",
                }
            },
        ),
    )
    page.locator("#source-load").click()
    expect(page.locator("#reload-error")).to_contain_text(
        "Incomplete treestamp markers"
    )
    expect(page.locator('.source-row[data-path="README.md"]')).to_have_attribute(
        "aria-selected", "true"
    )
    expect(page.locator("#source-load")).to_be_enabled()
    expect(page.locator("#source-create")).to_be_disabled()


def test_abandoning_repository_choices_returns_to_accepted_draft(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    region = page.locator("#region").text_content()
    address = page.url
    draft = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    page.locator(".wordmark").click()
    page.locator("#entry-browse").click()
    choose(page, "src")
    page.locator("#entry-change-repo").click()
    page.locator("#entry-url").fill("fixture/something-else")
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#region")).to_have_text(region)
    assert page.url == address
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == draft


def test_late_browse_response_cannot_reopen_the_chooser_after_return(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    pending = []
    page.route("**/api/browse*", lambda route: pending.append(route))
    page.locator(".wordmark").click()
    page.locator("#entry-browse").click()
    expect(page.locator("#source-browser")).to_contain_text("Loading repository")
    page.locator("#entry-change-repo").click()
    page.locator("#entry-return-welcome").click()
    assert len(pending) == 1
    pending[0].fulfill(
        json={"entries": [{"path": ".", "parent": None, "name": ".", "kind": "dir"}]}
    )
    expect(page.locator("#entry")).to_be_hidden()
    expect(page.locator("#workspace")).to_be_visible()


@pytest.mark.parametrize(
    ("path", "action"), [("src", "#source-create"), ("README.md", "#source-load")]
)
def test_source_actions_wait_for_browsing_and_opening(
    page: Page, service: str, path: str, action: str
) -> None:
    browsing: list[Route] = []
    opening: list[Route] = []
    page.route("**/api/browse*", lambda route: browsing.append(route))
    page.goto(f"{service}/fixture/repo")
    expect(page.locator(".source-tree")).to_have_attribute("aria-busy", "true")
    for selector in ("#source-create", "#source-load"):
        expect(page.locator(selector)).to_be_visible()
        expect(page.locator(selector)).to_be_disabled()
    assert len(browsing) == 1
    browsing[0].continue_()
    choose(page, path)
    expect(page.locator(action)).to_be_enabled()

    page.route("**/api/preview", lambda route: opening.append(route))
    page.locator(action).click()
    expect(page.locator(".source-tree")).to_have_attribute("aria-disabled", "true")
    for selector in ("#source-create", "#source-load"):
        expect(page.locator(selector)).to_be_visible()
        expect(page.locator(selector)).to_be_disabled()
    expect(page.locator("#entry-change-repo")).to_be_disabled()
    assert len(opening) == 1
    opening[0].continue_()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#reload-settings")).to_be_hidden()


def test_source_actions_require_a_valid_selection(page: Page, service: str) -> None:
    page.route("**/api/browse*", lambda route: route.fulfill(json={"entries": []}))
    page.goto(f"{service}/fixture/repo")
    expect(page.locator(".source-tree")).to_have_attribute("aria-busy", "false")
    expect(page.locator("#source-create")).to_be_disabled()
    expect(page.locator("#source-load")).to_be_disabled()
    expect(page.locator("#workspace")).to_be_hidden()


def test_resume_waits_for_acceptance_before_leaving_entry(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.add_init_script("""const originalFetch = window.fetch;
        window.fetch = async (url, init) => {
            const response = await originalFetch(url, init);
            if (url === '/api/op') await new Promise(resolve => {
                window.finishRestore = resolve;
            });
            return response;
        };""")
    page.goto(service + "/")
    expect(page.locator("#entry-welcome")).to_be_visible()
    assert page.evaluate("typeof window.finishRestore") == "undefined"
    page.locator("#entry-return-welcome").click()
    page.wait_for_function("() => typeof window.finishRestore === 'function'")
    expect(page.locator("#entry-return-welcome")).to_be_disabled()
    expect(page.locator("#entry-browse")).to_be_disabled()
    expect(page.locator("#explore-example")).to_be_disabled()
    expect(page.locator("#workspace")).to_be_hidden()
    page.evaluate("window.finishRestore()")
    expect(page.locator("#entry")).to_be_hidden()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#rows .row")).to_have_count(9)


@pytest.mark.parametrize("width", [390, 1280])
def test_wordmark_returns_to_landing_for_repository_and_source_choices(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.locator(".wordmark").click()
    expect(page.locator("#entry-welcome")).to_be_visible()
    expect(page.locator("#reload-settings")).to_be_hidden()
    page.locator("#entry-return-welcome").click()
    page.locator(".wordmark").click()
    page.locator("#entry-browse").click()
    expect(page.locator("#reload-settings")).to_be_visible()
    expect(page.locator("#entry-welcome")).to_be_hidden()
    expect(page.locator("#load-target")).to_have_text("fixture/repo")


def test_back_and_wordmark_navigation_preserve_the_current_tree(
    page: Page, service: str
) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.locator('.row[data-path="src"]').focus()
    page.locator("#row-note").click()
    page.locator("#note-text").fill("Keep this work")
    page.locator("#note-save").click()
    expect(page.locator("#region")).to_contain_text("Keep this work")
    region = page.locator("#region").text_content()
    address = page.url
    record = page.evaluate("localStorage.getItem('treestamp.current-draft')")

    page.locator(".wordmark").click()
    page.locator("#entry-browse").click()
    expect(page.locator("#entry-change-repo")).to_have_text("Back")
    page.locator("#entry-change-repo").click()
    expect(page.locator("#entry-welcome")).to_be_visible()
    expect(page.locator("#entry-url")).to_have_value("fixture/repo")
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#workspace")).to_be_visible()

    page.locator(".wordmark").click()
    expect(page.locator("#entry-welcome")).to_be_visible()
    expect(page.locator("#workspace")).to_be_hidden()
    assert page.url == address
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == record
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#region")).to_have_text(region)
    expect(page.locator("#tab-editor")).to_be_focused()


@pytest.mark.parametrize("width", [390, 768, 1280])
def test_entry_controls_are_readable_and_fit_without_full_width_mobile_button(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.goto(service + "/")
    page.evaluate("document.fonts.ready")
    for selector in ["#entry-form label", "#explore-example"]:
        assert page.locator(selector).evaluate(
            "element => parseFloat(getComputedStyle(element).fontSize) >= 16"
        )
    expect(page.locator("#explore-example")).to_have_css("text-decoration-line", "none")
    expect(page.locator("#explore-example")).to_have_css("border-top-style", "solid")
    page.locator("#entry-url").fill("fixture/repo")
    button = page.locator("#entry-create").bounding_box()
    field = page.locator("#entry-url").bounding_box()
    assert button is not None and field is not None
    assert button["width"] < field["width"]
    expect(page.locator(".entry-description")).to_have_count(0)
    page.locator("#entry-browse").click()
    expect(page.locator("#source-create")).to_be_enabled()
    assert page.locator(".entry-instructions").evaluate(
        "element => parseFloat(getComputedStyle(element).fontSize) >= 16"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_wordmark_does_not_abandon_an_initial_tree_request(
    page: Page, service: str
) -> None:
    page.add_init_script("""const originalFetch = window.fetch;
        window.fetch = async (url, init) => {
            const response = await originalFetch(url, init);
            if (String(url).startsWith('/api/preview')) {
                await new Promise(resolve => {
                    window.finishOpening = resolve;
                    document.documentElement.dataset.openingPending = "true";
                });
            }
            return response;
        };""")
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("html")).to_have_attribute("data-opening-pending", "true")
    page.locator(".wordmark").click()
    expect(page.locator("#entry")).to_be_hidden()
    expect(page.locator("#workspace")).to_be_visible()
    page.evaluate("window.finishOpening()")
    expect(page.locator("#rows .row")).to_have_count(9)
    expect(page.locator("#rows")).to_have_attribute("aria-busy", "false")


@pytest.mark.parametrize(
    ("width", "height"), [(320, 568), (390, 844), (768, 1024), (1280, 900)]
)
def test_picker_gives_tree_the_space_and_keeps_actions_at_its_foot(
    page: Page, service: str, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row")).to_have_count(9)
    page.route(
        "**/api/browse*",
        lambda route: route.fulfill(
            json={
                "entries": [
                    {"path": ".", "parent": None, "name": ".", "kind": "dir"},
                    *[
                        {
                            "path": f"file-{i}.md",
                            "parent": ".",
                            "name": f"file-{i}.md",
                            "kind": "file",
                        }
                        for i in range(60)
                    ],
                ]
            }
        ),
    )
    page.locator(".wordmark").click()
    page.locator("#entry-browse").click()
    expect(page.locator("#source-create")).to_be_enabled()
    page.evaluate("document.fonts.ready")
    instructions = page.locator(".entry-instructions p")
    expect(instructions).to_have_count(2)
    first = instructions.first.bounding_box()
    second = instructions.last.bounding_box()
    assert first and second
    assert first["y"] + first["height"] <= second["y"]
    tree = page.locator(".source-tree")
    bounds = tree.bounding_box()
    assert bounds is not None
    # Stacked guidance may take more than half a short screen; retain a useful
    # group of complete entries while the tree scrolls independently below it.
    visible_rows = tree.evaluate("""node => {
        const viewport = node.getBoundingClientRect();
        return [...node.querySelectorAll('.source-row')].filter(row => {
            const bounds = row.getBoundingClientRect();
            return bounds.top >= viewport.top && bounds.bottom <= viewport.bottom;
        }).length;
    }""")
    assert visible_rows >= MIN_VISIBLE_PICKER_ROWS
    assert tree.evaluate("node => node.scrollHeight > node.clientHeight")
    page.locator('.source-row[data-path="file-59.md"]').click()
    expect(page.locator("#source-load")).to_be_enabled()
    expect(page.locator("#source-create")).to_be_disabled()
    create = page.locator("#source-create")
    load = page.locator("#source-load")
    expect(create).to_be_in_viewport(ratio=1)
    expect(load).to_be_in_viewport(ratio=1)
    create_bounds = create.bounding_box()
    load_bounds = load.bounding_box()
    assert create_bounds is not None and load_bounds is not None
    assert create_bounds["y"] == pytest.approx(load_bounds["y"], abs=1)
    assert create_bounds["x"] + create_bounds["width"] <= load_bounds["x"]
    assert create_bounds["y"] >= bounds["y"] + bounds["height"]
    assert page.evaluate("document.documentElement.scrollHeight <= innerHeight")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert tree.evaluate("node => node.scrollTop > 0")
    page.locator("#entry-change-repo").click()
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#workspace")).to_be_visible()
