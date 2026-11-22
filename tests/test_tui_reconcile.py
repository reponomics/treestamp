"""Single-tree placement journeys use real document loads and keyboard input."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Input, ListView, Rule, Static

from treestamp.document import write_document
from treestamp.editor import EditorController
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings
from treestamp.tui import TreestampApp
from treestamp.tui_dialogs import DocumentChoiceScreen, PreviewScreen, PromptScreen
from treestamp.tui_reconcile import (
    PlacementChoiceScreen,
    PlacementConfirmScreen,
    ReconcileScreen,
)

from .conftest import Repo, run_cli

if TYPE_CHECKING:
    from textual.pilot import Pilot

NOTES = {"old/a.py": "First annotation", "old/b.py": "Second annotation"}


def load_stale(repo: Repo) -> EditorController:
    """Move two annotated rows into a previously collapsed existing directory."""
    for path in ("old/a.py", "old/b.py", "pkg/existing.py"):
        repo.write(path)
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())
    session = editor.state.session
    session.expand("old")
    for path, note in NOTES.items():
        session.set_annotation(path, note)
    write_document(editor.document(), repo.path / "tree.md", create=True)
    repo.git("mv", "old/a.py", "pkg/first.py")
    repo.git("mv", "old/b.py", "pkg/second.py")
    editor.adopt(editor.prepare_load("tree.md"))
    return editor


@pytest.fixture
def stale(repo: Repo) -> EditorController:
    return load_stale(repo)


def text_of(widget: Static) -> str:
    rendered = widget.render()
    return getattr(rendered, "plain", str(rendered))


async def press(pilot: Pilot[bool], *keys: str) -> None:
    await pilot.press(*keys)
    await pilot.pause()


async def opened(pilot: Pilot[bool], *, skip_group: bool = True) -> ReconcileScreen:
    assert isinstance(pilot.app.screen, PlacementChoiceScreen)
    await press(pilot, "enter")
    screen = pilot.app.screen
    assert isinstance(screen, ReconcileScreen)
    if (
        skip_group
        and screen.state.current.is_dir
        and not screen.state.current.annotation
    ):
        await press(pilot, "s")
    return screen


def selected(screen: ReconcileScreen) -> str:
    assert screen.tree_view.index is not None
    return screen.rows[screen.tree_view.index][0].path


def test_browse_one_tree_place_each_annotation_and_write(
    stale: EditorController, repo: Repo
) -> None:
    async def journey() -> None:
        app = TreestampApp(stale)
        before = stale.region_text()
        collapsed = stale.state.session.collapsed.copy()
        saved = repo.read_bytes("tree.md")
        async with app.run_test() as pilot:
            screen = await opened(pilot)
            assert len(screen.query(ListView)) == 1
            assert screen.tree_view.has_focus
            assert screen.state.current.path == "old/a.py"
            assert selected(screen) == ""
            await press(pilot, "down", "right", "right", "down")
            assert selected(screen) == "pkg/first.py"
            assert screen.state.current.path == "old/a.py"
            assert stale.state.session.collapsed == collapsed
            assert stale.region_text() == before
            await press(pilot, "enter")
            assert stale.state.session.annotations["pkg/first.py"] == NOTES["old/a.py"]
            assert "pkg" not in stale.state.session.collapsed
            assert NOTES["old/a.py"] in stale.region_text()
            assert screen.state.current.path == "old/b.py"
            assert selected(screen) == "pkg/first.py"
            await press(pilot, "down", "enter")
            assert screen.state.current is None
            assert screen.state.remaining == 0
            assert len(screen.state.placed) == 2
            assert app.screen is not screen
            assert stale.state.reconciliation is None
            assert repo.read_bytes("tree.md") == saved
            await press(pilot, "w")
        assert NOTES["old/a.py"] in repo.read("tree.md")
        assert NOTES["old/b.py"] in repo.read("tree.md")

    asyncio.run(journey())


def test_skip_and_undo_are_available_only_before_entering_editor(
    stale: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(stale)
        before = stale.region_text()
        async with app.run_test() as pilot:
            screen = await opened(pilot)
            await press(pilot, "s")
            assert screen.state.current.path == "old/b.py"
            assert screen.state.skipped == ["old/a.py"]
            await press(pilot, "u")
            assert screen.state.current.path == "old/a.py"
            assert not screen.state.skipped
            await press(pilot, "s", "s")
            assert app.screen is not screen
            assert stale.state.reconciliation is None
            assert stale.region_text() == before
            main_screen = app.screen
            await press(pilot, "r")
            assert app.screen is main_screen

    asyncio.run(journey())


def test_escape_keeps_placements_and_skips_remaining_without_reopen(
    stale: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(stale)
        async with app.run_test() as pilot:
            screen = await opened(pilot)
            await press(pilot, "down", "right", "right", "down", "enter", "escape")
            assert app.screen is not screen
            assert stale.state.reconciliation is None
            assert stale.state.session.annotations["pkg/first.py"] == NOTES["old/a.py"]
            assert "pkg/second.py" not in stale.state.session.annotations
            main_screen = app.screen
            await press(pilot, "r")
            assert app.screen is main_screen

    asyncio.run(journey())


def test_replacement_confirmation_cancel_accept_and_undo(
    stale: EditorController,
) -> None:
    stale.state.session.set_annotation("pkg/existing.py", "Keep this note")

    async def journey() -> None:
        app = TreestampApp(stale)
        async with app.run_test() as pilot:
            screen = await opened(pilot)
            await press(pilot, "down", "right", "right", "enter")
            assert isinstance(app.screen, PlacementConfirmScreen)
            await press(pilot, "escape")
            assert (
                stale.state.session.annotations["pkg/existing.py"] == "Keep this note"
            )
            assert screen.state.current.path == "old/a.py"
            await press(pilot, "enter", "y")
            assert (
                stale.state.session.annotations["pkg/existing.py"] == NOTES["old/a.py"]
            )
            assert screen.state.current.path == "old/b.py"
            await press(pilot, "u")
            assert (
                stale.state.session.annotations["pkg/existing.py"] == "Keep this note"
            )
            assert screen.state.current.path == "old/a.py"

    asyncio.run(journey())


def test_file_annotation_rejects_folder_with_a_browsing_hint(
    stale: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(stale)
        async with app.run_test() as pilot:
            screen = await opened(pilot)
            await press(pilot, "down", "enter")
            assert selected(screen) == "pkg"
            assert screen.state.current.path == "old/a.py"
            assert not screen.state.placed
            assert "browse" in text_of(screen.message_widget)
            await press(pilot, "right", "right")
            assert selected(screen) == "pkg/existing.py"

    asyncio.run(journey())


def test_revealing_hidden_destinations_is_only_browsing_until_placement(
    stale: EditorController,
) -> None:
    stale.state.session.hide("pkg/first.py")

    async def journey() -> None:
        app = TreestampApp(stale)
        before = stale.region_text()
        hidden = stale.state.session.hidden.copy()
        async with app.run_test() as pilot:
            screen = await opened(pilot)
            await press(pilot, "down", "right", "H")
            assert "pkg/first.py" in [node.path for node, _ in screen.rows]
            assert screen.browser.show_hidden
            assert not stale.state.session.show_hidden
            assert stale.state.session.hidden == hidden
            assert stale.region_text() == before
            await press(pilot, "right", "down", "enter")
            assert stale.state.session.annotations["pkg/first.py"] == NOTES["old/a.py"]
            assert not stale.state.session.is_hidden("pkg/first.py")
            assert NOTES["old/a.py"] in stale.region_text()

    asyncio.run(journey())


def test_details_exposes_full_source_annotation_and_destination(
    stale: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(stale)
        async with app.run_test() as pilot:
            screen = await opened(pilot)
            await press(pilot, "down", "right", "right", "question_mark")
            details = app.screen
            assert isinstance(details, PreviewScreen)
            assert "old/a.py" in details.text
            assert NOTES["old/a.py"] in details.text
            assert "pkg/existing.py" in details.text
            await press(pilot, "escape")
            assert app.screen is screen
            assert selected(screen) == "pkg/existing.py"

    asyncio.run(journey())


@pytest.mark.parametrize("size", [(80, 24), (60, 20)])
def test_long_source_and_annotation_keep_one_row_and_leave_space_for_tree(
    repo: Repo, size: tuple[int, int]
) -> None:
    name = "source_" + "long_" * 20 + ".py"
    note = "A detailed annotation that needs the separate details view. " * 12
    repo.write("old/" + name)
    repo.write("destination/keep.py")
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())
    editor.state.session.expand("old")
    editor.state.session.set_annotation("old/" + name, note)
    write_document(editor.document(), repo.path / "tree.md", create=True)
    repo.git("mv", "old/" + name, "destination/new.py")
    editor.adopt(editor.prepare_load("tree.md"))

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test(size=size) as pilot:
            screen = await opened(pilot)
            assert screen.source_widget.region.height == 1
            separator = screen.query_one(Rule)
            assert separator.region.y >= screen.source_widget.region.bottom
            assert separator.region.bottom <= screen.tree_view.region.y
            assert separator.region.height > 0
            assert screen.note_widget.region.height == 1
            assert screen.tree_view.region.height >= size[1] - 8
            for widget in screen.query("ListView, Static"):
                assert widget.region.height > 0
                assert widget.region.y >= 0
                assert widget.region.bottom <= size[1]
                assert widget.region.right <= size[0]
            await press(pilot, "question_mark")
            assert isinstance(app.screen, PreviewScreen)
            assert name in app.screen.text
            assert note.strip() in app.screen.text

    asyncio.run(journey())


def test_long_replacement_confirmation_keeps_response_keys_on_screen(
    stale: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(stale)
        async with app.run_test(size=(60, 20)) as pilot:
            screen = await opened(pilot)
            # Long filenames and nested paths can produce arbitrarily long prompts.
            message = "Replace the annotation on " + "/".join(
                ["long-directory-name"] * 40
            )
            app.push_screen(PlacementConfirmScreen(message))
            await pilot.pause()
            dialog = app.screen
            assert isinstance(dialog, PlacementConfirmScreen)
            panel = dialog.query_one(".confirm-panel")
            keys = dialog.query_one("#placement-confirm-keys", Static)
            assert panel.region.y >= 0
            assert panel.region.bottom <= 20
            assert keys.region.bottom <= 20
            assert keys.region.height > 0
            scroll = dialog.query_one(VerticalScroll)
            assert scroll.max_scroll_y > 0
            await press(pilot, "escape")
            assert app.screen is screen

    asyncio.run(journey())


def test_new_document_has_no_relink_queue(repo: Repo) -> None:
    repo.write("only.py")
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            assert not isinstance(app.screen, (PlacementChoiceScreen, ReconcileScreen))
            main_screen = app.screen
            await press(pilot, "r")
            assert app.screen is main_screen

    asyncio.run(journey())


@pytest.mark.parametrize("key", ["escape", "n"])
def test_declining_placement_enters_updated_editor_without_writing(
    stale: EditorController, repo: Repo, key: str
) -> None:
    async def journey() -> None:
        app = TreestampApp(stale)
        draft = stale.region_text()
        saved = repo.read_bytes("tree.md")
        async with app.run_test() as pilot:
            assert isinstance(app.screen, PlacementChoiceScreen)
            assert len(app.screen.query(ListView)) == 0
            await press(pilot, key)
            assert not isinstance(app.screen, (PlacementChoiceScreen, ReconcileScreen))
            assert stale.state.reconciliation is None
            assert stale.region_text() == draft
            assert repo.read_bytes("tree.md") == saved
            main_screen = app.screen
            await press(pilot, "r")
            assert app.screen is main_screen

    asyncio.run(journey())


def test_explicit_cli_load_offers_placement_before_editing(
    stale: EditorController, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def journey(app: TreestampApp) -> bool | None:
        async with app.run_test() as pilot:
            assert isinstance(app.screen, PlacementChoiceScreen)
            await press(pilot, "y")
            assert isinstance(app.screen, ReconcileScreen)
            await press(pilot, "escape")
            assert app.editor.state.reconciliation is None
        return app.return_value

    monkeypatch.setattr(TreestampApp, "run", lambda app: asyncio.run(journey(app)))
    assert run_cli("--load", "tree.md") == (0, "", "")


def test_startup_load_offers_placement_after_adopting_document(
    stale: EditorController, repo: Repo
) -> None:
    seed = EditorController(capture_snapshot(repo.path), Settings())

    async def journey() -> None:
        app = TreestampApp(seed, startup_document=Path("tree.md"))
        async with app.run_test() as pilot:
            assert isinstance(app.screen, DocumentChoiceScreen)
            await press(pilot, "l")
            assert isinstance(app.screen, PromptScreen)
            app.screen.query_one(Input).value = "tree.md"
            await press(pilot, "enter")
            assert isinstance(app.screen, PlacementChoiceScreen)
            await press(pilot, "enter")
            assert isinstance(app.screen, ReconcileScreen)
            assert app.screen.state.total == 2

    asyncio.run(journey())


def test_up_to_date_loaded_document_enters_editor_without_prompt(repo: Repo) -> None:
    repo.write("only.py")
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())
    editor.state.session.set_annotation("only.py", "Kept in place")
    write_document(editor.document(), repo.path / "tree.md", create=True)
    editor.adopt(editor.prepare_load("tree.md"))

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            assert not isinstance(app.screen, (PlacementChoiceScreen, ReconcileScreen))
            assert editor.state.session.annotations["only.py"] == "Kept in place"
            assert not editor.dirty
            await press(pilot, "r")
            assert not isinstance(app.screen, ReconcileScreen)

    asyncio.run(journey())


def directory_stale(repo: Repo, *, unmatched: bool = False) -> EditorController:
    for path in ("old/branch/a.py", "old/branch/deep/b.py", "keep.py"):
        repo.write(path)
    repo.add(".")
    editor = EditorController(capture_snapshot(repo.path), Settings())
    for directory in ("old", "old/branch", "old/branch/deep"):
        editor.state.session.expand(directory)
    for path, note in {
        "old/branch/a.py": "First child",
        "old/branch/deep": "Nested directory",
        "old/branch/deep/b.py": "Nested child",
    }.items():
        editor.state.session.set_annotation(path, note)
    write_document(editor.document(), repo.path / "tree.md", create=True)
    repo.git("mv", "old", "destination")
    if unmatched:
        repo.git("mv", "destination/branch/a.py", "destination/a.py")
    editor.adopt(editor.prepare_load("tree.md"))
    return editor


def test_unannotated_grandparent_places_recursive_annotations_and_enters_editor(
    repo: Repo,
) -> None:
    editor = directory_stale(repo)

    async def journey() -> None:
        app = TreestampApp(editor)
        saved = repo.read_bytes("tree.md")
        async with app.run_test() as pilot:
            screen = await opened(pilot, skip_group=False)
            assert screen.state.current.path == "old"
            assert not screen.state.current.annotation
            assert screen.state.total == 3
            await press(pilot, "down", "enter")
            assert app.screen is not screen
            assert editor.state.reconciliation is None
            assert screen.state.placed_count == 3
            assert editor.state.session.annotations == {
                "destination/branch/a.py": "First child",
                "destination/branch/deep": "Nested directory",
                "destination/branch/deep/b.py": "Nested child",
            }
            assert "Nested child" in editor.region_text()
            assert repo.read_bytes("tree.md") == saved

    asyncio.run(journey())


def test_directory_batch_leaves_unmatched_child_and_undo_restores_whole_batch(
    repo: Repo,
) -> None:
    editor = directory_stale(repo, unmatched=True)

    async def journey() -> None:
        app = TreestampApp(editor)
        before = editor.region_text()
        collapsed = editor.state.session.collapsed.copy()
        async with app.run_test() as pilot:
            screen = await opened(pilot, skip_group=False)
            await press(pilot, "down", "enter")
            assert app.screen is screen
            assert screen.state.current.path == "old/branch/a.py"
            assert screen.state.remaining == 1
            assert screen.state.placed_count == 2
            assert "destination/a.py" not in editor.state.session.annotations
            assert (
                editor.state.session.annotations["destination/branch/deep/b.py"]
                == "Nested child"
            )
            await press(pilot, "u")
            assert app.screen is screen
            assert screen.state.current.path == "old"
            assert screen.state.remaining == 3
            assert not screen.state.placed
            assert editor.region_text() == before
            assert editor.state.session.collapsed == collapsed

    asyncio.run(journey())
