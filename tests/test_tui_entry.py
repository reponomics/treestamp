"""Visual source browsing chooses filesystem entries without typing paths."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from textual.widgets import Static

from treestamp.document import write_document
from treestamp.editor import EditorController
from treestamp.gitio import Snapshot, capture_snapshot
from treestamp.model import Settings, build_tree
from treestamp.tui import TreestampApp
from treestamp.tui_entry import SourceChoiceScreen

from .conftest import Repo


def seed(repo: Repo) -> EditorController:
    return EditorController(
        Snapshot(repo.path, repo.path, build_tree([]), ""), Settings()
    )


@pytest.mark.parametrize("size", [(80, 24), (40, 20)])
def test_source_picker_keyboard_and_compact_geometry(
    repo: Repo, size: tuple[int, int]
) -> None:
    repo.write("src/nested/leaf.py")
    repo.write("plain.md", "No markers here.")
    repo.add(".")

    async def journey() -> None:
        app = TreestampApp(seed(repo), choose_source=True)
        async with app.run_test(size=size) as pilot:
            screen = app.screen
            assert isinstance(screen, SourceChoiceScreen)
            for selector in (
                "#source-heading",
                "#source-tree",
                "#source-selection",
                "#source-open",
                "#source-help",
            ):
                assert screen.query_one(selector).region in screen.region
            assert screen.source_tree.size.height >= 3
            assert screen.current.path == repo.path
            await pilot.press("down", "right", "right")
            assert screen.current.path == repo.path / "src/nested"
            await pilot.press("left")
            assert screen.current.path == repo.path / "src"
            await pilot.press("left")
            assert repo.path / "src" not in screen.expanded
            await pilot.press("home", "end")
            assert screen.current.path == repo.path / "plain.md"
            assert str(screen.open_button.label) == "Load treestamp from document"
            await pilot.press("enter")
            assert app.screen is screen
            assert screen.current.path.name == "plain.md"
            assert str(screen.error.render())
            assert screen.open_button.region in screen.region
            assert screen.query_one("#source-help").region in screen.region
            await pilot.press("escape")
        assert app.return_value is False

    asyncio.run(journey())


def test_pointer_selection_and_action_create_only_selected_subtree(repo: Repo) -> None:
    repo.write("src/leaf")
    repo.write("untracked.md", "No markers")
    repo.add("src")

    async def journey() -> None:
        app = TreestampApp(seed(repo), choose_source=True)
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, SourceChoiceScreen)
            assert any(row.path.name == "untracked.md" for row in screen.rows)
            assert all(row.path.name != ".git" for row in screen.rows)
            await pilot.click(screen.source_tree.children[1])
            assert screen.current.path.name == "src"
            assert app.screen is screen
            await pilot.click("#source-open")
            await pilot.pause()
            assert app.session.settings.root == "src"
            assert app.editor.state.document_path is None
            assert not isinstance(app.screen, SourceChoiceScreen)
            await pilot.press("q")

    asyncio.run(journey())


@pytest.mark.skipif(os.name == "nt", reason="requires symlink support")
def test_symlinks_are_visible_but_not_followed_or_accepted(
    repo: Repo, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("outside")
    (repo.path / "linked").symlink_to(outside, target_is_directory=True)
    (repo.path / "broken").symlink_to(tmp_path / "missing")

    async def journey() -> None:
        app = TreestampApp(seed(repo), choose_source=True)
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, SourceChoiceScreen)
            await pilot.press("end", "right", "enter")
            assert screen.current.path.name == "linked"
            assert screen.open_button.disabled
            assert screen.current.path not in screen.expanded
            assert all(row.path.name != "secret.md" for row in screen.rows)
            assert "symbolic link" in str(screen.error.render())
            await pilot.press("escape")

    asyncio.run(journey())


@pytest.mark.skipif(os.name == "nt", reason="raw filename bytes require POSIX")
@pytest.mark.parametrize(
    "name", ["odd-\x1b[31m.md", os.fsdecode(b"odd-\xff\x1b[31m.md")]
)
def test_raw_filename_identity_and_terminal_control_escaping(
    repo: Repo, name: str
) -> None:
    try:
        repo.write(name, "plain document")
    except OSError:
        pytest.skip("Filesystem rejects raw non-UTF-8 filenames")

    async def journey() -> None:
        app = TreestampApp(seed(repo), choose_source=True)
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, SourceChoiceScreen)
            await pilot.press("end", "enter")
            assert app.screen is screen
            assert screen.current.path.name == name
            label = screen.label(screen.current)
            assert "\x1b" not in label and "\\u001b" in label
            if "\udcff" in name:
                assert "\\udcff" in label
            assert screen.query_one("#source-selection", Static)
            await pilot.press("escape")

    asyncio.run(journey())


def test_pointer_opens_folder_then_loads_nested_document(repo: Repo) -> None:
    repo.write("src/leaf")
    repo.add("src")
    (repo.path / "docs").mkdir()
    document = repo.path / "docs/tree.md"
    source = EditorController(capture_snapshot(repo.path), Settings())
    write_document(source.document(), document, create=True)

    async def journey() -> None:
        app = TreestampApp(seed(repo), choose_source=True)
        async with app.run_test(size=(40, 20)) as pilot:
            screen = app.screen
            assert isinstance(screen, SourceChoiceScreen)
            index = next(
                i for i, row in enumerate(screen.rows) if row.path.name == "docs"
            )
            await pilot.click(screen.source_tree.children[index])
            assert screen.folder_button.region in screen.region
            assert screen.open_button.region in screen.region
            await pilot.click("#source-folder")
            await pilot.pause()
            assert repo.path / "docs" in screen.expanded
            index = next(
                i for i, row in enumerate(screen.rows) if row.path.name == "tree.md"
            )
            await pilot.click(screen.source_tree.children[index])
            assert not screen.folder_button.display
            await pilot.click("#source-open")
            await pilot.pause()
            assert app.editor.state.document_path == document
            assert not isinstance(app.screen, SourceChoiceScreen)
            await pilot.press("q")

    asyncio.run(journey())


def test_unreadable_folder_keeps_error_visible_after_refresh(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocked = repo.path / "blocked"
    blocked.mkdir()
    original = Path.iterdir

    def listing(path: Path):
        if path == blocked:
            raise PermissionError("permission denied")
        return original(path)

    monkeypatch.setattr(Path, "iterdir", listing)

    async def journey() -> None:
        app = TreestampApp(seed(repo), choose_source=True)
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, SourceChoiceScreen)
            await pilot.press("down", "right")
            await pilot.pause()
            assert screen.current.path == blocked
            assert "permission denied" in str(screen.error.render())
            await pilot.press("home")
            await pilot.pause()
            assert not str(screen.error.render())
            await pilot.press("escape")

    asyncio.run(journey())


def test_enter_activates_focused_folder_control_without_starting_editor(
    repo: Repo,
) -> None:
    repo.write("docs/nested.md", "No markers")

    async def journey() -> None:
        app = TreestampApp(seed(repo), choose_source=True)
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, SourceChoiceScreen)
            await pilot.press("down", "tab")
            assert app.focused is screen.folder_button
            await pilot.press("enter")
            await pilot.pause()
            assert app.screen is screen
            assert screen.current.path == repo.path / "docs"
            assert screen.current.path in screen.expanded
            assert any(row.path.name == "nested.md" for row in screen.rows)
            await pilot.press("tab", "enter")
            assert app.screen is screen
            assert screen.current.path not in screen.expanded
            await pilot.press("escape")

    asyncio.run(journey())
