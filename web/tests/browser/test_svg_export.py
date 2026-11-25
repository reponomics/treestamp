"""SVG export shows and delivers one accepted artifact without changing its source."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Page, Route, expect  # noqa: E402

from treestamp.document import parse_document, render_region  # noqa: E402
from treestamp.svg import SvgAppearance, parse_svg, render_svg  # noqa: E402

from .conftest import _build_fixture, _git  # noqa: E402
from .conftest import service as start_service

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.browser


def open_svg_export(page: Page, service: str) -> None:
    page.goto(f"{service}/fixture/repo?root=.")
    expect(page.locator("#rows .row").first).to_be_visible()
    page.get_by_role("tab", name="Export", exact=True).click()
    page.locator("#output-format").select_option("svg")


@pytest.fixture(scope="module")
def svg_service(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    fixture = _build_fixture(tmp_path_factory.mktemp("svg-browser") / "repo")
    document = parse_document((fixture.path / "README.md").read_bytes())
    (fixture.path / "assets").mkdir()
    (fixture.path / "assets/tree.svg").write_text(
        render_svg(document, SvgAppearance(theme="dark")), encoding="utf-8"
    )
    (fixture.path / "assets/adaptive.svg").write_text(
        render_svg(document, SvgAppearance(theme="adaptive")), encoding="utf-8"
    )
    (fixture.path / "assets/future.svg").write_text(
        render_svg(document, SvgAppearance(theme="dark")).replace(
            'style="continuous"', 'style="future-layout"'
        ),
        encoding="utf-8",
    )
    _git(fixture.path, "add", ".")
    _git(fixture.path, "commit", "-qm", "editable SVG")
    yield from start_service.__wrapped__(fixture)


@pytest.mark.parametrize("width", [320, 1280])
def test_preview_copy_and_download_share_bytes_and_preserve_text_source(
    page: Page, service: str, width: int
) -> None:
    page.set_viewport_size({"width": width, "height": 568 if width == 320 else 900})
    page.add_init_script(
        "Object.defineProperty(navigator, 'clipboard', "
        "{value: {writeText: async text => {window.copiedSVG = text}}})"
    )
    with page.expect_response("**/api/export/svg") as export_response:
        open_svg_export(page, service)
    expect(page.locator("#svg-download")).to_be_enabled()
    expect(page.locator("#svg-image")).to_be_visible()
    expect(page.locator("#copy")).to_be_hidden()
    original_address = page.url
    text = page.locator("#region").text_content()
    assert page.locator("#svg-image").get_attribute("src").startswith("blob:")
    svg = export_response.value.json()["variants"]["adaptive"]
    artifact = parse_svg(svg.encode())
    assert artifact.appearance.theme == "adaptive"
    assert render_region(artifact.document) == text

    page.locator("#svg-copy").click()
    expect(page.locator("#svg-status")).to_have_text("SVG source copied.")
    assert page.evaluate("window.copiedSVG") == svg
    with page.expect_download() as download_info:
        page.locator("#svg-download").click()
    download = download_info.value
    assert download.suggested_filename == "treestamp.svg"
    assert download.path().read_text(encoding="utf-8") == svg
    assert page.url == original_address

    page.locator("#svg-size").click()
    expect(page.locator("#svg-preview")).to_have_attribute("data-actual-size", "true")
    page.locator("#svg-size").click()
    expect(page.locator("#svg-size")).to_have_text("Actual size")
    page.locator("#output-format").select_option("markdown")
    expect(page.locator("#region")).to_be_visible()
    expect(page.locator("#copy")).to_be_visible()
    expect(page.locator("#region")).to_have_text(text)
    assert page.url == original_address


@pytest.mark.parametrize(
    "theme, ink, background",
    [("light", 0, "rgb(255, 255, 255)"), ("dark", 255, "rgb(13, 17, 23)")],
)
def test_fixed_appearance_is_independent_of_app_theme_for_text_export(
    page: Page, service: str, theme: str, ink: int, background: str
) -> None:
    page.add_init_script("localStorage.setItem('treestamp-theme', 'dark')")
    open_svg_export(page, service)
    expect(page.locator("#svg-download")).to_be_enabled()
    address = page.url
    expect(page.locator("#svg-preview")).to_have_attribute("data-theme", "adaptive")
    page.locator("#svg-theme").select_option(theme)
    expect(page.locator("#svg-download")).to_be_enabled()
    page.wait_for_function(_IMAGE_USES_INK, arg=ink)
    page.locator("#theme-toggle").click()
    expect(page.locator("#svg-theme")).to_have_value(theme)
    expect(page.locator("#svg-preview")).to_have_attribute("data-theme", theme)
    expect(page.locator("#svg-preview")).to_have_css("background-color", background)
    page.wait_for_function(_IMAGE_USES_INK, arg=ink)
    assert page.url == address


# Inspect the pixels of the real decoded image, not its source attributes: the
# browser must apply the SVG media query using the embedding app's color scheme.
_IMAGE_USES_INK = """expected => {
    const image = document.querySelector('#svg-image');
    if (!image.complete || !image.naturalWidth) return false;
    const canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    const context = canvas.getContext('2d');
    context.drawImage(image, 0, 0);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let solid = 0;
    for (let i = 0; i < pixels.length; i += 4) {
        if (pixels[i + 3] < 250) continue;
        solid += 1;
        if (pixels[i] !== expected || pixels[i + 1] !== expected || pixels[i + 2] !== expected) return false;
    }
    return solid > 10;
}"""


@pytest.mark.parametrize("loaded", [False, True])
def test_adaptive_preview_follows_app_theme_without_changing_artifact(
    page: Page, svg_service: str, loaded: bool
) -> None:
    page.emulate_media(color_scheme="light")
    page.add_init_script("localStorage.setItem('treestamp-theme', 'dark')")
    if loaded:
        page.goto(f"{svg_service}/fixture/repo?document=assets/adaptive.svg")
        expect(page.locator("#rows .row").first).to_be_visible()
        page.locator("#tab-stamp").click()
        page.locator("#output-format").select_option("svg")
    else:
        open_svg_export(page, svg_service)
    expect(page.locator("#svg-download")).to_be_enabled()
    expect(page.locator("#svg-theme")).to_have_value("adaptive")
    expect(page.locator("#svg-image")).to_have_css("color-scheme", "dark")
    page.wait_for_function(_IMAGE_USES_INK, arg=255)
    address = page.url
    cached = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    image_url = page.locator("#svg-image").get_attribute("src")
    with page.expect_download() as before:
        page.locator("#svg-download").click()
    original = before.value.path().read_bytes()
    assert parse_svg(original).appearance.theme == "adaptive"

    page.locator("#theme-toggle").click()
    expect(page.locator("#svg-image")).to_have_css("color-scheme", "light")
    page.wait_for_function(_IMAGE_USES_INK, arg=0)
    page.emulate_media(color_scheme="dark")
    page.wait_for_function(_IMAGE_USES_INK, arg=0)
    expect(page.locator("#svg-theme")).to_have_value("adaptive")
    assert page.locator("#svg-image").get_attribute("src") == image_url
    with page.expect_download() as after:
        page.locator("#svg-download").click()
    assert after.value.path().read_bytes() == original
    assert page.url == address
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == cached


def test_failed_generation_removes_stale_image_and_disables_actions(
    page: Page, service: str
) -> None:
    page.add_init_script(
        "window.revokedSVG = []; const revoke = URL.revokeObjectURL; "
        "URL.revokeObjectURL = url => {window.revokedSVG.push(url); revoke(url)}"
    )
    open_svg_export(page, service)
    expect(page.locator("#svg-download")).to_be_enabled()
    old_url = page.locator("#svg-image").get_attribute("src")
    page.route(
        "**/api/export/svg",
        lambda route: route.fulfill(
            status=422, json={"error": {"message": "Image exceeds the size limit."}}
        ),
    )
    page.locator("#output-format").select_option("markdown")
    page.locator("#output-format").select_option("svg")
    expect(page.locator("#svg-status")).to_contain_text("Image exceeds")
    expect(page.locator("#svg-download")).to_be_disabled()
    expect(page.locator("#svg-copy")).to_be_disabled()
    expect(page.locator("#svg-image")).to_be_hidden()
    assert old_url in page.evaluate("window.revokedSVG")
    page.unroute("**/api/export/svg")
    page.locator("#tab-editor").click()
    page.locator("#tab-stamp").click()
    page.locator("#output-format").select_option("svg")
    expect(page.locator("#svg-download")).to_be_enabled()


def test_pending_edits_disable_export_until_new_image_is_ready(
    page: Page, service: str
) -> None:
    open_svg_export(page, service)
    expect(page.locator("#svg-download")).to_be_enabled()
    old_url = page.locator("#svg-image").get_attribute("src")
    pending: list[Route] = []
    page.route("**/api/op", lambda route: pending.append(route))
    page.locator("#tab-editor").click()
    page.locator('.row[data-path="docs"] .name').click()
    page.wait_for_timeout(50)
    assert pending
    page.locator("#tab-stamp").click()
    page.locator("#output-format").select_option("svg")
    expect(page.locator("#svg-download")).to_be_disabled()
    expect(page.locator("#svg-copy")).to_be_disabled()
    pending.pop().continue_()
    expect(page.locator("#svg-download")).to_be_enabled()
    assert page.locator("#svg-image").get_attribute("src") != old_url


@pytest.mark.parametrize("filename", ["tree.svg", "future.svg", "adaptive.svg"])
def test_loaded_svg_starts_with_markdown_and_retains_appearance_and_filename(
    page: Page, svg_service: str, filename: str
) -> None:
    expected_theme = "adaptive" if filename == "adaptive.svg" else "dark"
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{svg_service}/fixture/repo?document=assets/{filename}")
    expect(page.locator("#rows .row").first).to_be_visible()
    page.locator("#tab-stamp").click()
    expect(page.locator("#output-format")).to_have_value("markdown")
    page.locator("#output-format").select_option("svg")
    expect(page.locator("#svg-theme")).to_have_value(expected_theme)
    expect(page.locator("#svg-source-notice")).to_contain_text(
        "loaded from SVG metadata"
    )
    if filename == "future.svg":
        expect(page.locator("#svg-source-notice")).to_contain_text("using continuous")
    expect(page.locator("#svg-download")).to_be_enabled()
    with page.expect_download() as download_info:
        page.locator("#svg-download").click()
    assert download_info.value.suggested_filename == filename
    address = page.url
    page.locator("#svg-theme").select_option("light")
    expect(page.locator("#svg-download")).to_be_enabled()
    assert page.url == address
    expect(page.locator("#svg-source-notice")).to_contain_text(
        "loaded from SVG metadata"
    )
    if filename == "future.svg":
        expect(page.locator("#svg-source-notice")).to_contain_text("using continuous")
    page.locator("#output-format").select_option("markdown")
    expect(page.locator("#region")).to_contain_text("treestamp:start")
    expect(page.locator("#document")).to_have_value(f"assets/{filename}")
    page.locator("#tab-editor").click()
    page.locator("#reset-tree").click()
    page.locator("#reset-confirm").click()
    expect(page.locator("#reset-dialog")).to_be_hidden()
    page.locator("#tab-stamp").click()
    page.locator("#output-format").select_option("svg")
    expect(page.locator("#svg-theme")).to_have_value(expected_theme)
    expect(page.locator("#svg-source-notice")).to_contain_text(
        "loaded from SVG metadata"
    )


def test_clipboard_failure_keeps_download_available(page: Page, service: str) -> None:
    page.add_init_script(
        "Object.defineProperty(navigator, 'clipboard', "
        "{value: {writeText: async () => {throw new Error('denied')}}})"
    )
    open_svg_export(page, service)
    expect(page.locator("#svg-copy")).to_be_enabled()
    page.locator("#svg-copy").click()
    expect(page.locator("#svg-status")).to_have_text(
        "Copy failed. Download the SVG instead."
    )
    expect(page.locator("#svg-download")).to_be_enabled()


@pytest.fixture(scope="module")
def svg_placement_service(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    from .test_placement import build_placement_fixture

    fixture = build_placement_fixture(tmp_path_factory.mktemp("svg-transfer") / "repo")
    document = parse_document((fixture.path / "README.md").read_bytes())
    (fixture.path / "tree.svg").write_text(
        render_svg(document, SvgAppearance(theme="dark")).replace(
            'style="continuous"', 'style="future-layout"'
        ),
        encoding="utf-8",
    )
    _git(fixture.path, "add", ".")
    _git(fixture.path, "commit", "-qm", "SVG awaiting note transfer")
    yield from start_service.__wrapped__(fixture)


def test_transfer_into_svg_preserves_source_and_exports_transferred_notes(
    page: Page, svg_placement_service: str
) -> None:
    page.goto(f"{svg_placement_service}/fixture/repo?document=tree.svg")
    expect(page.locator("#placement-dialog")).to_be_visible()
    page.locator('#placement-rows [data-path="tools"]').click()
    page.locator("#placement-place").click()
    expect(page.locator("#placement-source")).to_have_text("retired.py")
    page.locator("#placement-finish").click()
    expect(page.locator("#placement-dialog")).to_be_hidden()
    page.locator("#tab-stamp").click()
    expect(page.locator("#output-format")).to_have_value("markdown")
    page.locator("#output-format").select_option("svg")
    expect(page.locator("#svg-theme")).to_have_value("dark")
    expect(page.locator("#svg-source-notice")).to_contain_text("using continuous")
    expect(page.locator("#svg-download")).to_be_enabled()
    address = page.url
    with page.expect_download() as download_info:
        page.locator("#svg-download").click()
    download = download_info.value
    assert download.suggested_filename == "tree.svg"
    tree = parse_svg(download.path().read_bytes()).document.tree
    notes = {node.path: node.annotation for node in tree.walk()}
    assert notes["tools"] == "Data preparation tools"
    assert "Historical importer" not in notes.values()
    expect(page.locator("#document")).to_have_value("tree.svg")
    assert page.url == address


def test_failed_transfer_restores_previous_svg_export(
    page: Page, svg_placement_service: str
) -> None:
    page.goto(svg_placement_service + "/")
    page.locator("#explore-example").click()
    expect(page.locator("#rows .row").first).to_be_visible()
    page.locator("#tab-stamp").click()
    page.locator("#output-format").select_option("svg")
    page.locator("#svg-theme").select_option("dark")
    expect(page.locator("#svg-download")).to_be_enabled()
    with page.expect_download() as before_info:
        page.locator("#svg-download").click()
    previous = before_info.value.path().read_bytes()
    address = page.url
    region = page.locator("#region").text_content()
    saved = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    page.locator(".wordmark").click()

    def corrupt_transfer(route: Route) -> None:
        response = route.fetch()
        body = response.json()
        body["placement"]["current"] = None
        route.fulfill(response=response, json=body)

    page.route("**/api/preview", corrupt_transfer)
    page.locator("#entry-url").fill("fixture/repo")
    page.locator("#entry-load").click()
    expect(page.locator("#entry-error")).to_be_visible()
    expect(page.locator("#placement-dialog")).to_be_hidden()
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#output-format")).to_have_value("markdown")
    page.locator("#output-format").select_option("svg")
    page.locator("#svg-theme").select_option("dark")
    expect(page.locator("#svg-theme")).to_have_value("dark")
    expect(page.locator("#svg-download")).to_be_enabled()
    with page.expect_download() as after_info:
        page.locator("#svg-download").click()
    assert after_info.value.path().read_bytes() == previous
    expect(page.locator("#region")).to_have_text(region)
    assert page.url == address
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == saved


def bundle_for_request(route: Route) -> dict[str, object]:
    body = route.request.post_data_json
    document = parse_document(body["region"].encode())
    return {
        "variants": {
            theme: render_svg(document, SvgAppearance(theme=theme))
            for theme in ("adaptive", "light", "dark")
        }
    }


@pytest.mark.parametrize("loaded", [False, True])
def test_appearance_switches_use_one_bundle_without_changing_editor(
    page: Page, svg_service: str, loaded: bool
) -> None:
    calls: list[str] = []
    page.on(
        "request",
        lambda request: (
            calls.append(request.url)
            if "/api/export/svg" in request.url or "/api/op" in request.url
            else None
        ),
    )
    page.add_init_script(
        "Object.defineProperty(navigator, 'clipboard', "
        "{value: {writeText: async text => {window.copiedSVG = text}}})"
    )
    source = "?document=assets/tree.svg" if loaded else "?root=."
    page.goto(f"{svg_service}/fixture/repo{source}")
    expect(page.locator("#rows .row").first).to_be_visible()
    page.locator("#tab-stamp").click()
    expect(page.locator("#output-format")).to_have_value("markdown")
    assert not calls
    page.locator("#output-format").select_option("svg")
    expect(page.locator("#svg-download")).to_be_enabled()
    assert len(calls) == 1
    address = page.url
    cached = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    urls = set()
    for theme in ("light", "dark", "adaptive", "dark", "light"):
        page.locator("#svg-theme").select_option(theme)
        expect(page.locator("#svg-preview")).to_have_attribute("aria-busy", "false")
        expect(page.locator("#svg-download")).to_be_enabled()
        page.locator("#svg-copy").click()
        expect(page.locator("#svg-status")).to_have_text("SVG source copied.")
        assert (
            parse_svg(page.evaluate("window.copiedSVG").encode()).appearance.theme
            == theme
        )
        urls.add(page.locator("#svg-image").get_attribute("src"))
    assert len(urls) == 3 and len(calls) == 1
    assert page.url == address
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == cached

    page.locator("#svg-size").click()
    page.locator("#tab-editor").click()
    page.locator("#tab-stamp").click()
    expect(page.locator("#output-format")).to_have_value("markdown")
    expect(page.locator("#svg-image")).to_be_hidden()
    expect(page.locator("#svg-theme")).to_have_value("dark" if loaded else "adaptive")
    expect(page.locator("#svg-size")).to_have_text("Actual size")
    assert len(calls) == 1
    page.locator("#output-format").select_option("svg")
    expect(page.locator("#svg-download")).to_be_enabled()
    assert len(calls) == 2


def test_busy_and_rate_limited_exports_retry_then_deliver(
    page: Page, service: str
) -> None:
    page.clock.install()
    attempts: list[int] = []

    def respond(route: Route) -> None:
        attempts.append(len(attempts) + 1)
        if len(attempts) == 1:
            route.fulfill(
                status=503,
                headers={"Retry-After": "1"},
                json={"error": {"code": "svg_busy", "message": "busy"}},
            )
        elif len(attempts) == 2:
            route.fulfill(
                status=429,
                headers={"Retry-After": "2"},
                json={"error": {"code": "rate_limited", "message": "rate"}},
            )
        else:
            route.fulfill(json=bundle_for_request(route))

    page.route("**/api/export/svg", respond)
    open_svg_export(page, service)
    expect(page.locator("#svg-status")).to_contain_text("Waiting to try again")
    expect(page.locator("#svg-retry")).to_be_hidden()
    page.clock.fast_forward(1500)
    expect(page.locator("#svg-status")).to_contain_text("Waiting to try again")
    assert len(attempts) == 2
    page.clock.fast_forward(1000)
    assert len(attempts) == 2
    page.clock.fast_forward(1500)
    expect(page.locator("#svg-download")).to_be_enabled()
    expect(page.locator("#svg-status")).to_be_empty()
    assert len(attempts) == 3


@pytest.mark.parametrize("failure", ["busy", "pending", "decoding"])
def test_generation_deadline_offers_explicit_retry(
    page: Page, service: str, failure: str
) -> None:
    page.clock.install()
    if failure == "decoding":
        page.add_init_script(
            "window.decodeSVG = HTMLImageElement.prototype.decode; "
            "HTMLImageElement.prototype.decode = () => new Promise(() => {})"
        )
    attempts: list[Route] = []

    def respond(route: Route) -> None:
        attempts.append(route)
        if failure == "busy":
            route.fulfill(
                status=503,
                headers={"Retry-After": "60"},
                json={"error": {"code": "svg_busy"}},
            )
        elif failure == "decoding":
            route.fulfill(json=bundle_for_request(route))

    page.route("**/api/export/svg", respond)
    open_svg_export(page, service)
    expect(page.locator("#svg-preview")).to_have_attribute("aria-busy", "true")
    page.wait_for_timeout(50)
    assert attempts
    page.clock.fast_forward(30_001)
    expect(page.locator("#svg-status")).to_contain_text("Try again")
    expect(page.locator("#svg-retry")).to_be_visible()
    expect(page.locator("#svg-preview")).to_have_attribute("aria-busy", "false")
    expect(page.locator("#svg-download")).to_be_disabled()
    assert len(attempts) == 1
    page.unroute("**/api/export/svg")
    if failure == "decoding":
        page.evaluate("() => { HTMLImageElement.prototype.decode = window.decodeSVG; }")
    page.locator("#svg-retry").click()
    expect(page.locator("#svg-download")).to_be_enabled()
    expect(page.locator("#svg-retry")).to_be_hidden()


def test_leaving_export_cancels_retry_and_late_results_while_editing(
    page: Page, service: str
) -> None:
    pending: list[Route] = []
    page.route("**/api/export/svg", lambda route: pending.append(route))
    open_svg_export(page, service)
    expect(page.locator("#svg-preview")).to_have_attribute("aria-busy", "true")
    page.wait_for_timeout(50)
    assert pending
    late = pending.pop()
    bundle = bundle_for_request(late)
    page.locator("#tab-editor").click()
    with page.expect_response("**/api/op") as edited:
        page.locator('.row[data-path="docs"] .name').click()
    assert edited.value.ok
    late.fulfill(json=bundle)
    page.locator("#tab-stamp").click()
    expect(page.locator("#output-format")).to_have_value("markdown")
    expect(page.locator("#svg-preview")).to_have_attribute("aria-busy", "false")
    expect(page.locator("#svg-download")).to_be_disabled()
    expect(page.locator("#svg-image")).to_be_hidden()
    assert not pending


def test_leaving_export_stops_scheduled_retry(page: Page, service: str) -> None:
    page.clock.install()
    attempts: list[int] = []

    def busy(route: Route) -> None:
        attempts.append(1)
        route.fulfill(
            status=503,
            headers={"Retry-After": "2"},
            json={"error": {"code": "svg_busy"}},
        )

    page.route("**/api/export/svg", busy)
    open_svg_export(page, service)
    expect(page.locator("#svg-status")).to_contain_text("Waiting")
    page.locator("#tab-editor").click()
    page.clock.fast_forward(35_000)
    assert len(attempts) == 1
    page.locator("#tab-stamp").click()
    expect(page.locator("#output-format")).to_have_value("markdown")
    expect(page.locator("#svg-retry")).to_be_hidden()


def test_invalid_export_does_not_retry_automatically(page: Page, service: str) -> None:
    page.clock.install()
    attempts: list[int] = []

    def invalid(route: Route) -> None:
        attempts.append(1)
        route.fulfill(status=422, json={"error": {"message": "Image is too large."}})

    page.route("**/api/export/svg", invalid)
    open_svg_export(page, service)
    expect(page.locator("#svg-status")).to_contain_text("Image is too large")
    expect(page.locator("#svg-retry")).to_be_visible()
    page.clock.fast_forward(35_000)
    assert len(attempts) == 1


@pytest.mark.parametrize("leave", [False, True])
def test_late_clipboard_failure_cannot_replace_current_export_status(
    page: Page, service: str, leave: bool
) -> None:
    page.add_init_script(
        "Object.defineProperty(navigator, 'clipboard', "
        "{value: {writeText: () => new Promise((resolve, reject) => {window.rejectCopy = reject})}})"
    )
    open_svg_export(page, service)
    expect(page.locator("#svg-copy")).to_be_enabled()
    page.locator("#svg-copy").click()
    page.wait_for_function("typeof window.rejectCopy === 'function'")
    if leave:
        page.locator("#tab-editor").click()
        page.locator("#tab-stamp").click()
    else:
        page.locator("#svg-theme").select_option("dark")
    page.evaluate("window.rejectCopy(new Error('late denial'))")
    expect(page.locator("#svg-status")).to_be_empty()
    expect(page.locator("#svg-copy")).to_have_text("Copy SVG")
