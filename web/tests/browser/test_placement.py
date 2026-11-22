"""A stale document is resettled once, before accepting an editing draft."""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from .conftest import Fixture, _git, service

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Locator, Page, expect  # noqa: E402

pytestmark = pytest.mark.browser
DRAFT = "localStorage.getItem('treestamp.current-draft')"


def build_placement_fixture(path: Path) -> Fixture:
    """A renamed directory, matching grandchildren, and one retired note."""
    from treestamp.document import Document, write_document
    from treestamp.gitio import capture_snapshot
    from treestamp.model import Settings
    from treestamp.session import TreeSession

    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test")
    files = {
        "old-tools/formats/csv.py": "# CSV support\n",
        "old-tools/report.py": "# Report generation\n",
        "keep.py": "# Stable file\n",
        "retired.py": "# Retired implementation\n",
        "README.md": "# Field guide\n\n<!-- treestamp:start -->\n<!-- treestamp:end -->\n",
    }
    for relative, content in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "Create project")
    old = _git(path, "rev-parse", "HEAD")
    settings = Settings()
    snapshot = capture_snapshot(path, "HEAD")
    session = TreeSession(snapshot.tree, settings)
    for node in snapshot.tree.walk():
        if node.is_dir:
            session.expand(node.path)
    for name, note in {
        "old-tools": "Data preparation tools",
        "old-tools/formats/csv.py": "Normalize incoming columns",
        "old-tools/report.py": "Build the weekly report",
        "retired.py": "Historical importer",
        "keep.py": "Keep this existing note",
    }.items():
        session.set_annotation(name, note)
    session.hide("README.md")
    write_document(
        Document(session.printed_tree(), settings, session.saved_hidden()),
        path / "README.md",
    )
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "Document project")
    (path / "old-tools").rename(path / "tools")
    (path / "retired.py").unlink()
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "Rename tools and retire importer")
    return Fixture(path, old, _git(path, "rev-parse", "HEAD"))


@pytest.fixture(scope="session")
def placement_repo(tmp_path_factory: pytest.TempPathFactory) -> Fixture:
    return build_placement_fixture(tmp_path_factory.mktemp("placement") / "repo")


@pytest.fixture(scope="session")
def placement_service(placement_repo: Fixture) -> Iterator[str]:
    yield from service.__wrapped__(placement_repo)


def open_document(page: Page, base: str) -> None:
    page.goto(base + "/")
    page.get_by_label("Public GitHub repository").fill("fixture/repo")
    page.get_by_role("button", name="Browse repository", exact=True).click()
    page.locator('#source-browser [data-path="README.md"]').click()
    page.get_by_role("button", name="Load treestamp from document", exact=True).click()
    expect(page.locator("#placement-dialog")).to_be_visible()
    expect(page.locator("#placement-choice-title")).to_have_text(
        "4 notes lost their place."
    )


def start(page: Page, base: str) -> None:
    open_document(page, base)
    page.locator("#placement-start").click()
    expect(page.locator("#placement-source")).to_have_text("old-tools/")


def destination(page: Page, path: str) -> Locator:
    return page.locator(f'#placement-rows [data-path="{path}"]')


def expect_provisional(page: Page) -> None:
    expect(page.locator("#workspace")).to_be_hidden()
    expect(page.locator("#rows .row")).to_have_count(0)
    assert page.evaluate(DRAFT) is None


def test_recursive_folder_placement_undo_and_finish_enter_editor(
    page: Page, placement_service: str
) -> None:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    start(page, placement_service)
    expect_provisional(page)
    destination(page, "tools").click()
    page.locator("#placement-place").click()
    expect(page.locator("#placement-source")).to_have_text("retired.py")
    expect(page.locator("#placement-progress")).to_have_text("1 left · 3 placed")
    expect(destination(page, "tools")).to_contain_text("Data preparation tools")
    expect_provisional(page)
    page.locator("#placement-undo").click()
    expect(page.locator("#placement-source")).to_have_text("old-tools/")
    expect(page.locator("#placement-progress")).to_have_text("4 left · 0 placed")
    expect(destination(page, "tools")).not_to_contain_text("Data preparation tools")
    expect(page.locator("#placement-undo")).to_be_disabled()
    page.locator("#placement-place").click()
    expect(page.locator("#placement-source")).to_have_text("retired.py")
    page.locator("#placement-skip").click()
    expect(page.locator("#placement-dialog")).to_be_hidden()
    expect(page.locator("#entry")).to_be_hidden()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#rows .row").first).to_be_focused()
    region = page.locator("#region")
    for note in (
        "Data preparation tools",
        "Normalize incoming columns",
        "Build the weekly report",
        "Keep this existing note",
    ):
        expect(region).to_contain_text(note)
    expect(region).not_to_contain_text("Historical importer")
    expect(region).not_to_contain_text("old-tools")
    assert page.evaluate(DRAFT) is not None
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.locator("#copy").click()
    expect(page.locator("#copy-status")).to_contain_text("Paste into README.md")
    assert page.evaluate("navigator.clipboard.readText()") == region.text_content()
    assert errors == []


@pytest.mark.parametrize("restore", ["fragment", "local"])
def test_decline_accepts_updated_tree_and_restore_does_not_prompt_again(
    page: Page, placement_service: str, restore: str
) -> None:
    open_document(page, placement_service)
    expect_provisional(page)
    page.locator("#placement-decline").click()
    expect(page.locator("#workspace")).to_be_visible()
    region = page.locator("#region").text_content()
    assert region and "Keep this existing note" in region
    assert "Data preparation tools" not in region
    assert "Historical importer" not in region
    if restore == "fragment":
        page.reload()
    else:
        page.goto(placement_service + "/")
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#region")).to_have_text(region)
    expect(page.locator("#placement-dialog")).to_be_hidden()


def test_browsing_destinations_does_not_expand_the_accepted_draft(
    page: Page, placement_service: str
) -> None:
    start(page, placement_service)
    tools = destination(page, "tools")
    expect(tools).to_have_attribute("aria-expanded", "false")
    tools.click()
    page.locator("#placement-folder").click()
    expect(destination(page, "tools/formats")).to_be_visible()
    destination(page, "tools/formats").click()
    page.keyboard.press("ArrowRight")
    expect(destination(page, "tools/formats/csv.py")).to_be_visible()
    expect_provisional(page)
    page.locator("#placement-finish").click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator('#rows .row[data-path="tools"]')).to_be_visible()
    expect(page.locator('#rows .row[data-path="tools/formats"]')).to_have_count(0)
    expect(page.locator("#region")).not_to_contain_text("Normalize incoming columns")


def test_replacement_requires_a_choice_and_preserves_existing_note_on_cancel(
    page: Page, placement_service: str
) -> None:
    start(page, placement_service)
    page.keyboard.press("s")
    expect(page.locator("#placement-source")).to_have_text("old-tools/formats/csv.py")
    destination(page, "keep.py").click()
    page.keyboard.press("Enter")
    expect(page.locator("#placement-replace-dialog")).to_be_visible()
    expect(page.locator("#placement-replace-cancel")).to_be_focused()
    page.locator("#placement-replace-cancel").click()
    expect(page.locator("#placement-replace-dialog")).to_be_hidden()
    expect(destination(page, "keep.py")).to_contain_text("Keep this existing note")
    expect(page.locator("#placement-source")).to_have_text("old-tools/formats/csv.py")
    expect(destination(page, "keep.py")).to_be_focused()
    page.keyboard.press("Enter")
    page.locator("#placement-replace-accept").click()
    expect(page.locator("#placement-source")).to_have_text("old-tools/report.py")
    expect(destination(page, "keep.py")).to_contain_text("Normalize incoming columns")
    page.keyboard.press("u")
    expect(page.locator("#placement-source")).to_have_text("old-tools/formats/csv.py")
    expect(destination(page, "keep.py")).to_contain_text("Keep this existing note")
    page.locator("#placement-finish").click()
    expect(page.locator("#region")).to_contain_text("Keep this existing note")
    expect(page.locator("#region")).not_to_contain_text("Normalize incoming columns")


def test_failed_request_keeps_the_last_accepted_decision_and_can_retry(
    page: Page, placement_service: str
) -> None:
    start(page, placement_service)
    destination(page, "tools").click()
    page.locator("#placement-place").click()
    expect(page.locator("#placement-source")).to_have_text("retired.py")
    page.route(
        "**/api/placement",
        lambda route: route.fulfill(
            status=503, json={"error": {"message": "Please try again."}}
        ),
    )
    page.locator("#placement-undo").click()
    expect(page.locator("#placement-error")).to_contain_text("Please try again.")
    expect(page.locator("#placement-source")).to_have_text("retired.py")
    expect(page.locator("#placement-progress")).to_have_text("1 left · 3 placed")
    expect(destination(page, "tools")).to_contain_text("Data preparation tools")
    expect_provisional(page)
    page.unroute("**/api/placement")
    page.locator("#placement-undo").click()
    expect(page.locator("#placement-source")).to_have_text("old-tools/")
    expect(page.locator("#placement-error")).to_be_hidden()
    page.locator("#placement-finish").click()
    expect(page.locator("#region")).not_to_contain_text("Data preparation tools")


@pytest.mark.parametrize("width,height", [(1280, 900), (820, 900), (390, 844)])
def test_keyboard_and_layout_keep_one_source_above_one_destination_tree(
    page: Page, placement_service: str, width: int, height: int
) -> None:
    page.set_viewport_size({"width": width, "height": height})
    start(page, placement_service)
    first = page.locator("#placement-rows [role=treeitem]").first
    expect(first).to_be_focused()
    page.keyboard.press("ArrowDown")
    expect(destination(page, "tools")).to_be_focused()
    page.keyboard.press("ArrowRight")
    expect(destination(page, "tools/formats")).to_be_visible()
    page.keyboard.press("ArrowDown")
    expect(destination(page, "tools/formats")).to_be_focused()
    page.keyboard.press("ArrowLeft")
    expect(destination(page, "tools")).to_be_focused()
    page.keyboard.press("ArrowLeft")
    expect(destination(page, "tools/formats")).to_have_count(0)
    page.keyboard.press("ArrowUp")
    expect(first).to_be_focused()
    dialog = page.locator("#placement-dialog")
    assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth")
    for selector in (
        "#placement-source",
        "#placement-rows",
        "#placement-place",
        "#placement-skip",
        "#placement-undo",
        "#placement-finish",
    ):
        bounds = page.locator(selector).bounding_box()
        assert bounds is not None, selector
        assert bounds["x"] >= 0 and bounds["y"] >= 0, selector
        assert bounds["x"] + bounds["width"] <= width, selector
        assert bounds["y"] + bounds["height"] <= height, selector
    source = page.locator("#placement-source").bounding_box()
    tree = page.locator("#placement-rows").bounding_box()
    assert source and tree and source["y"] + source["height"] < tree["y"]


def test_another_document_load_starts_with_enabled_placement_controls(
    page: Page, placement_service: str
) -> None:
    start(page, placement_service)
    destination(page, "tools").click()
    page.locator("#placement-place").click()
    expect(page.locator("#placement-source")).to_have_text("retired.py")
    page.locator("#placement-skip").click()
    expect(page.locator("#workspace")).to_be_visible()
    page.locator("#submit").click()
    page.locator('#source-browser [data-path="README.md"]').click()
    page.locator("#reload").click()
    page.locator("#placement-start").click()
    expect(page.locator("#placement-source")).to_have_text("old-tools/")
    for selector in ("#placement-skip", "#placement-finish", "#placement-reveal"):
        expect(page.locator(selector)).to_be_enabled()
    page.locator("#placement-finish").click()
    expect(page.locator("#workspace")).to_be_visible()


def test_file_and_folder_destinations_make_incompatible_choices_unavailable(
    page: Page, placement_service: str
) -> None:
    start(page, placement_service)
    destination(page, "keep.py").click()
    expect(page.locator("#placement-place")).to_be_disabled()
    expect(page.locator("#placement-target-hint")).to_contain_text("Choose a folder")
    page.keyboard.press("Enter")
    expect(page.locator("#placement-source")).to_have_text("old-tools/")
    page.keyboard.press("s")
    expect(page.locator("#placement-source")).to_have_text("old-tools/formats/csv.py")
    destination(page, "tools").click()
    expect(page.locator("#placement-place")).to_be_disabled()
    expect(page.locator("#placement-folder")).to_be_enabled()
    expect(page.locator("#placement-target-hint")).to_contain_text("Choose a file")
    page.locator("#placement-finish").click()


def test_failed_new_document_placement_preserves_the_previous_saved_draft(
    page: Page, placement_service: str
) -> None:
    open_document(page, placement_service)
    page.locator("#placement-decline").click()
    expect(page.locator("#workspace")).to_be_visible()
    original = page.locator("#region").text_content()
    saved = page.evaluate(DRAFT)
    page.locator("#submit").click()
    page.locator('#source-browser [data-path="README.md"]').click()
    page.locator("#reload").click()
    page.locator("#placement-start").click()
    destination(page, "tools").click()
    page.locator("#placement-place").click()
    expect(page.locator("#placement-source")).to_have_text("retired.py")
    assert page.evaluate(DRAFT) == saved
    expect(page.locator("#region")).to_have_text(original)
    page.route("**/api/placement", lambda route: route.abort())
    page.locator("#placement-skip").click()
    expect(page.locator("#placement-error")).to_contain_text(
        "Your last decision is unchanged"
    )
    expect(page.locator("#placement-source")).to_have_text("retired.py")
    assert page.evaluate(DRAFT) == saved
    expect(page.locator("#region")).to_have_text(original)
    page.unroute("**/api/placement")
    page.locator("#placement-finish").click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#region")).to_contain_text("Data preparation tools")
    assert page.evaluate(DRAFT) != saved


def test_short_mobile_dialog_scrolls_to_all_actions_without_horizontal_clipping(
    page: Page, placement_service: str
) -> None:
    page.set_viewport_size({"width": 320, "height": 568})
    start(page, placement_service)
    dialog = page.locator("#placement-dialog")
    assert dialog.evaluate("element => element.scrollWidth <= element.clientWidth")
    for selector in (
        "#placement-undo",
        "#placement-skip",
        "#placement-place",
        "#placement-finish",
    ):
        control = page.locator(selector)
        control.scroll_into_view_if_needed()
        bounds = control.bounding_box()
        assert bounds is not None
        assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= 320
        assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 568
    page.locator("#placement-finish").click()
    expect(page.locator("#placement-dialog")).to_be_hidden()
    expect(page.locator("#workspace")).to_be_visible()


def place_folder_and_finish(page: Page) -> None:
    destination(page, "tools").click()
    page.locator("#placement-place").click()
    expect(page.locator("#placement-source")).to_have_text("retired.py")
    page.locator("#placement-skip").click()
    expect(page.locator("#placement-dialog")).to_be_hidden()
    expect(page.locator("#workspace")).to_be_visible()


@pytest.mark.parametrize("place_again", [True, False])
def test_reset_reloads_source_and_completes_placement_before_accepting_draft(
    page: Page, placement_service: str, place_again: bool
) -> None:
    start(page, placement_service)
    place_folder_and_finish(page)
    page.locator('.row[data-path="keep.py"] [data-action="note"]').click()
    page.locator("#note-text").fill("An edit after placing")
    page.locator("#note-save").click()
    expect(page.locator("#region")).to_contain_text("An edit after placing")
    previous = page.locator("#region").text_content()
    record = page.evaluate(DRAFT)
    address = page.url
    page.locator("#reset-tree").click()
    page.locator("#reset-confirm").click()
    expect(page.locator("#placement-dialog")).to_be_visible()
    expect(page.locator("#reset-dialog")).to_be_visible()
    expect(page.locator("#placement-start")).to_be_focused()
    assert page.evaluate(DRAFT) == record
    assert page.url == address
    expect(page.locator("#region")).to_have_text(previous)
    if place_again:
        page.locator("#placement-start").click()
        place_folder_and_finish(page)
        expect(page.locator("#region")).to_contain_text("Data preparation tools")
        expect(page.locator("#region")).to_contain_text("Normalize incoming columns")
    else:
        page.locator("#placement-decline").click()
        expect(page.locator("#region")).not_to_contain_text("Data preparation tools")
    expect(page.locator("#reset-dialog")).to_be_hidden()
    expect(page.locator("#region")).not_to_contain_text("An edit after placing")
    expect(page.locator("#region")).to_contain_text("Keep this existing note")
    assert page.evaluate(DRAFT) != record
    accepted = page.locator("#region").text_content()
    page.locator("#submit").click()
    warning = page.locator("#replace-draft-warning")
    if place_again:
        expect(warning).to_be_visible()
    else:
        expect(warning).to_be_hidden()
    page.locator("#entry-return").click()
    expect(page.locator("#region")).to_have_text(accepted)
    page.goto(placement_service + "/")
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#region")).to_have_text(accepted)
    expect(page.locator("#placement-dialog")).to_be_hidden()


def test_failed_reset_of_placed_document_preserves_storage_and_can_retry(
    page: Page, placement_service: str
) -> None:
    start(page, placement_service)
    place_folder_and_finish(page)
    previous = page.locator("#region").text_content()
    record = page.evaluate(DRAFT)
    address = page.url
    page.route(
        "**/api/preview",
        lambda route: route.fulfill(
            status=503, json={"error": {"message": "Snapshot unavailable."}}
        ),
    )
    page.locator("#reset-tree").click()
    page.locator("#reset-confirm").click()
    expect(page.locator("#reset-dialog .dialog-error")).to_contain_text(
        "Snapshot unavailable"
    )
    expect(page.locator("#placement-dialog")).to_be_hidden()
    expect(page.locator("#region")).to_have_text(previous)
    assert page.evaluate(DRAFT) == record
    assert page.url == address
    page.unroute("**/api/preview")
    page.locator("#reset-confirm").click()
    expect(page.locator("#placement-dialog")).to_be_visible()
    page.locator("#placement-decline").click()
    expect(page.locator("#reset-dialog")).to_be_hidden()
    expect(page.locator("#region")).not_to_contain_text("Data preparation tools")


def test_resume_progress_after_placement_preserves_notes_without_reopening_queue(
    page: Page, placement_service: str
) -> None:
    start(page, placement_service)
    place_folder_and_finish(page)
    previous = page.locator("#region").text_content()
    record = page.evaluate(DRAFT)
    address = page.url
    page.locator("#submit").click()
    expect(page.locator("#entry-return")).to_have_text("Resume progress")
    page.locator('#source-browser [data-path="tools"]').click()
    page.locator("#entry-return").click()
    expect(page.locator("#region")).to_have_text(previous)
    expect(page.locator("#placement-dialog")).to_be_hidden()
    page.locator(".wordmark").click()
    expect(page.locator("#entry-title")).to_have_text("Open another tree")
    page.locator("#entry-return-welcome").click()
    expect(page.locator("#workspace")).to_be_visible()
    expect(page.locator("#region")).to_have_text(previous)
    expect(page.locator("#placement-dialog")).to_be_hidden()
    assert page.evaluate(DRAFT) == record
    assert page.url == address
