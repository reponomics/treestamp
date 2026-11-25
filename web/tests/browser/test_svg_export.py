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
    (fixture.path / "assets/auto.svg").write_text(
        render_svg(document, SvgAppearance(theme="auto")), encoding="utf-8"
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
    svg = export_response.value.json()["svg"]
    artifact = parse_svg(svg.encode())
    assert artifact.appearance.theme == "auto"
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
    expect(page.locator("#svg-preview")).to_have_attribute("data-theme", "auto")
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
def test_automatic_preview_follows_app_theme_without_changing_artifact(
    page: Page, svg_service: str, loaded: bool
) -> None:
    page.emulate_media(color_scheme="light")
    page.add_init_script("localStorage.setItem('treestamp-theme', 'dark')")
    if loaded:
        page.goto(f"{svg_service}/fixture/repo?document=assets/auto.svg")
        expect(page.locator("#rows .row").first).to_be_visible()
        page.locator("#tab-stamp").click()
    else:
        open_svg_export(page, svg_service)
    expect(page.locator("#svg-download")).to_be_enabled()
    expect(page.locator("#svg-theme")).to_have_value("auto")
    expect(page.locator("#svg-image")).to_have_css("color-scheme", "dark")
    page.wait_for_function(_IMAGE_USES_INK, arg=255)
    address = page.url
    cached = page.evaluate("localStorage.getItem('treestamp.current-draft')")
    image_url = page.locator("#svg-image").get_attribute("src")
    with page.expect_download() as before:
        page.locator("#svg-download").click()
    original = before.value.path().read_bytes()
    assert parse_svg(original).appearance.theme == "auto"

    page.locator("#theme-toggle").click()
    expect(page.locator("#svg-image")).to_have_css("color-scheme", "light")
    page.wait_for_function(_IMAGE_USES_INK, arg=0)
    page.emulate_media(color_scheme="dark")
    page.wait_for_function(_IMAGE_USES_INK, arg=0)
    expect(page.locator("#svg-theme")).to_have_value("auto")
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
    page.locator("#svg-theme").select_option("dark")
    expect(page.locator("#svg-status")).to_contain_text("Image exceeds")
    expect(page.locator("#svg-download")).to_be_disabled()
    expect(page.locator("#svg-copy")).to_be_disabled()
    expect(page.locator("#svg-image")).to_be_hidden()
    assert old_url in page.evaluate("window.revokedSVG")
    page.unroute("**/api/export/svg")
    page.locator("#tab-editor").click()
    page.locator("#tab-stamp").click()
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
    expect(page.locator("#svg-download")).to_be_disabled()
    expect(page.locator("#svg-copy")).to_be_disabled()
    pending.pop().continue_()
    expect(page.locator("#svg-download")).to_be_enabled()
    assert page.locator("#svg-image").get_attribute("src") != old_url


@pytest.mark.parametrize("filename", ["tree.svg", "future.svg", "auto.svg"])
def test_loaded_svg_defaults_to_image_and_retains_appearance_and_filename(
    page: Page, svg_service: str, filename: str
) -> None:
    expected_theme = "auto" if filename == "auto.svg" else "dark"
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(f"{svg_service}/fixture/repo?document=assets/{filename}")
    expect(page.locator("#rows .row").first).to_be_visible()
    page.locator("#tab-stamp").click()
    expect(page.locator("#output-format")).to_have_value("svg")
    expect(page.locator("#svg-theme")).to_have_value(expected_theme)
    expect(page.locator("#svg-source-notice")).to_contain_text("regenerated")
    if filename == "future.svg":
        expect(page.locator("#svg-source-notice")).to_contain_text("using continuous")
    expect(page.locator("#svg-download")).to_be_enabled()
    with page.expect_download() as download_info:
        page.locator("#svg-download").click()
    assert download_info.value.suggested_filename == filename
    address = page.url
    page.locator("#svg-theme").select_option("light")
    expect(page.locator("#svg-download")).to_be_enabled()
    assert page.url != address
    expect(page.locator("#svg-source-notice")).to_contain_text("regenerated")
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
    expect(page.locator("#svg-source-notice")).to_contain_text("regenerated")


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
    expect(page.locator("#output-format")).to_have_value("svg")
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
    expect(page.locator("#output-format")).to_have_value("svg")
    expect(page.locator("#svg-theme")).to_have_value("dark")
    expect(page.locator("#svg-download")).to_be_enabled()
    with page.expect_download() as after_info:
        page.locator("#svg-download").click()
    assert after_info.value.path().read_bytes() == previous
    expect(page.locator("#region")).to_have_text(region)
    assert page.url == address
    assert page.evaluate("localStorage.getItem('treestamp.current-draft')") == saved
