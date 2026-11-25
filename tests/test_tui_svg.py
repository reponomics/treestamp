"""SVG export dialog keeps failures reversible and source updates explicit."""

import asyncio
from dataclasses import replace

import pytest
from textual.widgets import Input, Static

from treestamp import tui
from treestamp.artifacts import parse_artifact
from treestamp.editor import EditorController
from treestamp.model import Entry, Settings, build_tree
from treestamp.tui import TreestampApp
from treestamp.tui_dialogs import ConfirmScreen
from treestamp.tui_export import SvgExportScreen

from .conftest import Repo
from .test_editor import make_editor
from .test_editor_svg import load_svg
from .tui_support import press, rendered_text


@pytest.fixture
def editor(repo: Repo) -> EditorController:
    return make_editor(repo)


def test_export_save_and_cancel_preserve_source_and_dirty_state(repo: Repo) -> None:
    controller = load_svg(repo)
    baseline = controller.state.baseline
    controller.state.session.set_annotation("readme", "unsaved")

    async def journey() -> None:
        app = TreestampApp(controller)
        async with app.run_test() as pilot:
            await press(pilot, "e")
            screen = app.screen
            assert isinstance(screen, SvgExportScreen)
            screen.query_one(Input).value = "copy.svg"
            await pilot.click("#svg-export-save")
            await pilot.pause()
            assert not isinstance(app.screen, SvgExportScreen)
            assert "Saved SVG:" in rendered_text(app.status_widget)
            assert (
                parse_artifact(repo.read_bytes("copy.svg")).document
                == controller.document()
            )
            assert controller.state.baseline is baseline and controller.dirty
            assert controller.state.document_path == repo.path / "tree.svg"
            await press(pilot, "e", "escape")
            assert controller.state.baseline is baseline and controller.dirty
            await press(pilot, "w")
            assert not controller.dirty
            assert (
                parse_artifact(repo.read_bytes("tree.svg")).appearance.theme == "dark"
            )

    asyncio.run(journey())


def test_replacement_confirmation_detects_intervening_change(
    repo: Repo, editor: EditorController
) -> None:
    repo.write("copy.svg", "<svg/>")

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "e")
            screen = app.screen
            assert isinstance(screen, SvgExportScreen)
            field = screen.query_one(Input)
            field.value = "copy.svg"
            await pilot.click("#svg-export-save")
            await pilot.pause()
            assert isinstance(app.screen, ConfirmScreen)
            assert str(repo.path / "copy.svg") in rendered_text(
                app.screen.query_one("#confirmation", Static)
            )
            repo.write("copy.svg", "intervening content")
            await press(pilot, "y")
            assert app.screen is screen and field.value == "copy.svg"
            assert "changed" in rendered_text(
                screen.query_one("#svg-export-error", Static)
            )
            assert repo.read("copy.svg") == "intervening content"
            await pilot.click("#svg-export-save")
            await press(pilot, "n")
            assert app.screen is screen and field.value == "copy.svg"
            await pilot.click("#svg-export-save")
            await press(pilot, "y")
            assert not isinstance(app.screen, SvgExportScreen)
            assert parse_artifact(repo.read_bytes("copy.svg")) is not None
            assert editor.state.document_path is None

    asyncio.run(journey())


@pytest.mark.parametrize("destination", ["tree.svg", "README.md", "missing/copy.svg"])
def test_invalid_export_keeps_destination_and_dialog(
    repo: Repo, destination: str
) -> None:
    controller = load_svg(repo)
    original = repo.read_bytes("tree.svg")

    async def journey() -> None:
        app = TreestampApp(controller)
        async with app.run_test() as pilot:
            await press(pilot, "e")
            screen = app.screen
            assert isinstance(screen, SvgExportScreen)
            screen.query_one(Input).value = destination
            await pilot.click("#svg-export-save")
            await pilot.pause()
            assert app.screen is screen
            assert screen.query_one(Input).value == destination
            assert "Cannot save SVG" in rendered_text(
                screen.query_one("#svg-export-error", Static)
            )
            assert repo.read_bytes("tree.svg") == original
            assert not controller.dirty

    asyncio.run(journey())


def test_copy_svg_uses_complete_source_and_honest_terminal_status(
    editor: EditorController, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []
    monkeypatch.setattr(tui, "_clipboard_command", lambda: None)
    monkeypatch.setattr(
        TreestampApp, "copy_to_clipboard", lambda self, text: sent.append(text)
    )
    baseline = editor.state.baseline

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "e")
            app.screen.query_one(Input).value = ""
            await pilot.click("#svg-export-copy")
            await pilot.pause()
            assert not isinstance(app.screen, SvgExportScreen)
            assert sent == [editor.svg_text()]
            assert parse_artifact(sent[0].encode()).document == editor.document()
            assert "paste to confirm" in rendered_text(app.status_widget)
            assert editor.state.baseline is baseline

    asyncio.run(journey())


def test_clipboard_failure_retains_export_dialog(
    editor: EditorController, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise OSError("clipboard unavailable")

    monkeypatch.setattr(tui, "_clipboard_command", lambda: ["failed-clipboard"])
    monkeypatch.setattr(tui.subprocess, "run", fail)

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "e")
            screen = app.screen
            await pilot.click("#svg-export-copy")
            await pilot.pause()
            assert app.screen is screen
            assert "clipboard unavailable" in rendered_text(
                screen.query_one("#svg-export-error", Static)
            )
            assert screen.query_one(Input).value == "treestamp.svg"

    asyncio.run(journey())


def test_terminal_transport_limit_offers_file_save(
    editor: EditorController, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tui, "_clipboard_command", lambda: None)
    # Stay inside the image width limit while exceeding OSC 52's byte budget.
    tree = build_tree([Entry(f"file{index:03}.py") for index in range(200)])
    tree = replace(
        tree,
        children=tuple(
            replace(node, annotation="long note " * 40) for node in tree.children
        ),
    )
    editor = EditorController(replace(editor.state.snapshot, tree=tree), Settings())
    assert len(editor.svg_text().encode("utf-8")) > 100_000

    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "e")
            screen = app.screen
            await pilot.click("#svg-export-copy")
            await pilot.pause()
            assert app.screen is screen
            message = rendered_text(screen.query_one("#svg-export-error", Static))
            assert "transport limit" in message and "Save SVG" in message

    asyncio.run(journey())


def test_startup_can_load_svg_and_default_destination_avoids_source(repo: Repo) -> None:
    controller = load_svg(repo)
    repo.write("treestamp.svg", repo.read("tree.svg"))

    controller.adopt(controller.prepare_load("treestamp.svg"))

    async def journey() -> None:
        app = TreestampApp(controller)
        async with app.run_test() as pilot:
            assert controller.state.source_format == "svg"
            assert "SVG" in rendered_text(app.document_controls)
            assert "treestamp.svg" in rendered_text(app.document_controls)
            await press(pilot, "e")
            assert isinstance(app.screen, SvgExportScreen)
            assert app.screen.query_one(Input).value == ""

    asyncio.run(journey())


def test_new_tree_exports_automatic_svg_without_a_theme_selection(
    editor: EditorController,
) -> None:
    async def journey() -> None:
        app = TreestampApp(editor)
        async with app.run_test() as pilot:
            await press(pilot, "e")
            assert "Export SVG — Automatic" in " ".join(
                rendered_text(widget) for widget in app.screen.query(Static)
            )
            await pilot.click("#svg-export-save")
            await pilot.pause()
            source = (editor.state.snapshot.repo / "treestamp.svg").read_bytes()
            artifact = parse_artifact(source)
            assert artifact.appearance.theme == "auto"
            assert b"@media (prefers-color-scheme: dark)" in source
            assert editor.state.document_path is None

    asyncio.run(journey())
