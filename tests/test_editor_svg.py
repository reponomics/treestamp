"""SVG source identity, regeneration, and separate export publication."""

from dataclasses import replace

import pytest

from treestamp.artifacts import capture_export_destination, parse_artifact
from treestamp.document import parse_document, publish_write
from treestamp.editor import EditorController
from treestamp.errors import MarkerError
from treestamp.svg import render_svg
from treestamp.svg_metadata import SvgAppearance

from .conftest import Repo
from .test_editor import make_editor


def load_svg(repo: Repo, *, altered: bool = False) -> EditorController:
    editor = make_editor(repo)
    content = render_svg(editor.document(), SvgAppearance(theme="dark"))
    if altered:
        content = content.replace("Repository tree", "Manually edited drawing")
    repo.write("tree.svg", content)
    editor.adopt(editor.prepare_load("tree.svg"))
    return editor


def test_svg_load_regenerates_drawing_and_retains_original_baseline(repo: Repo) -> None:
    editor = load_svg(repo, altered=True)
    original = repo.read_bytes("tree.svg")
    assert editor.state.source_format == "svg"
    assert editor.state.svg_appearance.theme == "dark"
    assert "regenerated from embedded data" in editor.state.status
    assert editor.dirty
    assert repo.read_bytes("tree.svg") == original
    assert "Manually edited drawing" not in editor.svg_text()
    assert parse_document(editor.region_text().encode()).tree == editor.document().tree
    assert "<svg" not in editor.preview()
    editor.write("tree.svg")
    assert not editor.dirty
    # The write keeps the loaded file's line endings.
    written = repo.read_bytes("tree.svg").replace(b"\r\n", b"\n")
    assert written == editor.svg_text().encode()
    assert not editor.prepare_load("tree.svg").dirty


def test_svg_source_write_preserves_appearance_and_rejects_external_edit(
    repo: Repo,
) -> None:
    editor = load_svg(repo)
    editor.state.session.set_annotation("src/a", "changed")
    assert editor.dirty
    original = repo.read_bytes("tree.svg")
    repo.write_bytes("tree.svg", original.replace(b"Repository tree", b"Changed"))
    conflicting = repo.read_bytes("tree.svg")
    with pytest.raises(MarkerError, match="changed"):
        editor.write("tree.svg")
    assert repo.read_bytes("tree.svg") == conflicting
    assert editor.dirty
    repo.write_bytes("tree.svg", original)
    editor.write("tree.svg")
    saved = parse_artifact(repo.read_bytes("tree.svg"))
    assert saved is not None and saved.appearance.theme == "dark"
    assert (
        next(
            node for node in saved.document.tree.walk() if node.path == "src/a"
        ).annotation
        == "changed"
    )
    assert not editor.dirty


def test_appearance_changes_only_dirty_svg_source(repo: Repo) -> None:
    editor = make_editor(repo)
    repo.write("tree.md", editor.region_text())
    editor.adopt(editor.prepare_load("tree.md"))
    editor.state.svg_appearance = SvgAppearance(theme="dark")
    assert not editor.dirty
    editor = load_svg(repo)
    assert not editor.dirty
    editor.state.svg_appearance = replace(editor.state.svg_appearance, theme="light")
    assert editor.dirty


def test_export_creation_and_replacement_do_not_adopt_source(repo: Repo) -> None:
    editor = load_svg(repo)
    before = editor.state
    baseline = editor.state.baseline
    editor.state.session.set_annotation("src/a", "exported note")
    prepared = editor.prepare_svg_export("copy.svg")
    publish_write(prepared)
    assert editor.state is before and editor.state.baseline is baseline
    assert editor.state.document_path == repo.path / "tree.svg"
    assert editor.dirty
    assert parse_artifact(repo.read_bytes("copy.svg")).document == editor.document()
    with pytest.raises(MarkerError, match="exist"):
        editor.prepare_svg_export("copy.svg")
    previous = capture_export_destination(repo.path / "copy.svg", repository=repo.path)
    editor.state.session.set_annotation("src/a", "replacement")
    publish_write(editor.prepare_svg_export("copy.svg", expected=previous))
    assert editor.state.baseline is baseline
    assert parse_artifact(repo.read_bytes("copy.svg")).document == editor.document()


def test_export_refuses_racing_creation_and_replacement(repo: Repo) -> None:
    editor = make_editor(repo)
    prepared = editor.prepare_svg_export("copy.svg")
    repo.write("copy.svg", "another writer")
    with pytest.raises(MarkerError, match="exists"):
        publish_write(prepared)
    previous = capture_export_destination(repo.path / "copy.svg", repository=repo.path)
    prepared = editor.prepare_svg_export("copy.svg", expected=previous)
    repo.write("copy.svg", "changed after confirmation")
    with pytest.raises(MarkerError, match="changed"):
        publish_write(prepared)
    assert repo.read("copy.svg") == "changed after confirmation"


@pytest.mark.parametrize(
    "destination", ["tree.svg", "README.md", "missing/tree.svg", "../outside.svg"]
)
def test_export_rejects_source_and_invalid_destinations(
    repo: Repo, destination: str
) -> None:
    editor = load_svg(repo)
    before = repo.read_bytes("tree.svg")
    with pytest.raises(MarkerError):
        editor.prepare_svg_export(destination)
    assert repo.read_bytes("tree.svg") == before
    assert not editor.dirty


def test_svg_edit_rolls_back_when_result_exceeds_artifact_limit(repo: Repo) -> None:
    editor = load_svg(repo)
    before = editor.state.session.state()
    with pytest.raises(MarkerError, match="limit"), editor.edit():
        editor.state.session.set_annotation("readme", "large note " * 30_000)
    assert editor.state.session.state() == before
    assert not editor.dirty
