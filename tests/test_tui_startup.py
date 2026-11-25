"""CLI-selected sessions open the editor directly without source selection."""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import Static, TextArea

from treestamp.document import write_document
from treestamp.editor import EditorController
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings
from treestamp.tui import TreestampApp
from treestamp.tui_dialogs import PromptScreen

from .conftest import Repo, run_cli
from .tui_support import editor_fixture as editor_fixture
from .tui_support import press, rendered_text


@pytest.mark.parametrize("loaded", [False, True])
def test_retired_editor_actions_cannot_replace_the_draft(
    editor: EditorController, loaded: bool
) -> None:
    if loaded:
        write_document(
            editor.document(), editor.state.snapshot.repo / "tree.md", create=True
        )
        editor.adopt(editor.prepare_load("tree.md"))
    editor.state.session.set_annotation("readme", "Keep my edits")
    before = editor.state.session.state()
    document = editor.state.document_path

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "N", "l", "n")
            assert len(app.screen_stack) == 1
            assert app.session.state() == before
            assert app.editor.state.document_path == document
            controls = "\n".join(
                rendered_text(w) for w in app.query(Static).filter(".controls")
            )
            assert "New" not in controls and "Load" not in controls
            assert "Write new" not in controls
            await press(pilot, "?")
            help_text = app.screen.query_one(TextArea).text
            assert ("w               " in help_text) is loaded
            for obsolete in (
                "N               ",
                "l               ",
                "n               ",
                "new file",
            ):
                assert obsolete not in help_text

    asyncio.run(journey())


def test_new_root_opens_directly_and_style_edits_that_tree(
    editor: EditorController, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def journey(app: TreestampApp) -> bool | None:
        async with app.run_test() as pilot:
            assert len(app.screen_stack) == 1
            assert app.session.settings.root == "src"
            assert app.cursor.path == "" and not app.editor.dirty
            assert "pkg" in app.session.collapsed
            assert app.session.settings.root in rendered_text(
                app.query_one("#title", Static)
            )
            await press(pilot, "s")
            assert app.session.settings.style == "ascii" and app.editor.dirty
            assert app.session.settings.root == "src"
        return app.return_value

    def run(app: TreestampApp) -> bool | None:
        return asyncio.run(journey(app))

    monkeypatch.setattr(TreestampApp, "run", run)
    assert run_cli("new", "src") == (0, "", "")


@pytest.mark.parametrize("arguments", [(), ("new",)])
def test_fresh_start_enters_editor_without_a_picker_or_ignored_files(
    repo: Repo,
    editor: EditorController,
    monkeypatch: pytest.MonkeyPatch,
    arguments: tuple[str, ...],
) -> None:
    repo.write("README.md", "A project without a treestamp.\n")
    repo.write(".gitignore", "ignored/\n")
    repo.write("ignored/cache.bin")
    before = repo.read_bytes("README.md")

    async def journey(app: TreestampApp) -> bool | None:
        async with app.run_test() as pilot:
            assert len(app.screen_stack) == 1
            assert app.tree_view.has_focus
            assert app.tree_view.children
            assert app.editor.state.document_path is None
            assert app.editor.state.root == repo.path
            assert not app.editor.dirty
            assert "ignored" not in {node.path for node in app.session.root.walk()}
            await press(pilot, "q")
        return app.return_value

    def run(app: TreestampApp) -> bool | None:
        return asyncio.run(journey(app))

    monkeypatch.setattr(TreestampApp, "run", run)
    assert run_cli(*arguments) == (0, "", "")
    assert repo.read_bytes("README.md") == before


def test_empty_index_opens_editor_with_staging_guidance(repo: Repo) -> None:
    repo.write("untracked.txt")
    editor = EditorController(capture_snapshot(repo.path), Settings())

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            assert len(app.screen_stack) == 1
            assert not app.session.root.children
            assert "git add" in rendered_text(app.status_widget)
            assert app.tree_view.has_focus
            await press(pilot, "q")
        assert app.return_value is False

    asyncio.run(journey())


def test_cli_explicit_load_opens_document_without_startup_dialogs(
    repo: Repo, editor: EditorController, monkeypatch: pytest.MonkeyPatch
) -> None:
    editor.adopt(editor.prepare_new("src"))
    (repo.path / "docs").mkdir()
    write_document(
        editor.document(), editor.state.snapshot.repo / "docs/tree.md", create=True
    )
    before = repo.read_bytes("docs/tree.md")
    monkeypatch.chdir(repo.path / "docs")

    async def journey(app: TreestampApp) -> bool | None:
        async with app.run_test() as pilot:
            assert len(app.screen_stack) == 1
            assert app.editor.state.document_path == repo.path / "docs/tree.md"
            assert app.editor.state.snapshot.repo == repo.path
            assert app.session.settings.root == "src"
            assert app.tree_view.children
            assert not app.editor.dirty
            await press(pilot, "w")
            assert not isinstance(app.screen, PromptScreen)
            assert app.editor.state.document_path == repo.path / "docs/tree.md"
            assert "Wrote treestamped document" in rendered_text(app.status_widget)
            await press(pilot, "q")
        return app.return_value

    def run(app: TreestampApp) -> bool | None:
        return asyncio.run(journey(app))

    monkeypatch.setattr(TreestampApp, "run", run)
    assert run_cli("load", "tree.md") == (0, "", "")
    assert repo.read_bytes("docs/tree.md") == before
