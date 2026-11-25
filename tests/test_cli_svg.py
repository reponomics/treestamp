"""Public SVG conversion, source maintenance, and deliberate copy destinations."""

from dataclasses import replace

import pytest

from tests.cli_fixtures import stamp
from tests.conftest import run_cli
from treestamp.document import parse_document, render_region
from treestamp.svg import SvgAppearance, parse_svg, render_svg


@pytest.mark.parametrize("style", ["unicode", "ascii"])
@pytest.mark.parametrize("theme", ["auto", "light", "dark"])
def test_text_to_svg_to_text_and_source_update(repo, style, theme):
    source = stamp(repo)
    document = parse_document(source.read_bytes())
    document = replace(document, settings=replace(document.settings, style=style))
    source.write_text(render_region(document), encoding="utf-8")
    original = source.read_bytes()
    code, output, error = run_cli(
        "export",
        "--load",
        "README.md",
        "--format",
        "svg",
        "--stdout",
        "--theme",
        theme,
    )
    assert code == 0 and not error
    artifact = parse_svg(output.encode())
    assert artifact.appearance == SvgAppearance(theme=theme)
    assert render_region(artifact.document) == render_region(document)
    assert source.read_bytes() == original
    svg = repo.write("tree.svg", output)
    code, text, error = run_cli(
        "export", "--load", "tree.svg", "--format", "markdown", "--stdout"
    )
    assert code == 0 and not error
    assert parse_document(text.encode()) == artifact.document
    assert run_cli("check", "tree.svg")[0] == 0
    repo.write("new -> literal")
    repo.add("new -> literal")
    assert run_cli("check", "tree.svg")[0] == 1
    assert svg.read_text(encoding="utf-8") == output
    assert run_cli("update", "tree.svg")[0] == 0
    assert run_cli("check", "tree.svg")[0] == 0
    updated = parse_svg(svg.read_bytes())
    assert updated.appearance == artifact.appearance
    assert "new -> literal" in [node.name for node in updated.document.tree.walk()]
    assert source.read_bytes() == original
    assert run_cli("load", "tree.svg", "--print")[1] == render_region(updated.document)


def test_export_file_requires_explicit_replacement_and_leaves_source(repo):
    source = stamp(repo)
    original = source.read_bytes()
    args = ("export", "--load", "README.md", "--format", "svg", "--output", "tree.svg")
    assert run_cli(*args)[0] == 0
    exported = repo.read_bytes("tree.svg")
    assert parse_svg(exported).appearance.theme == "auto"
    assert run_cli(*args)[0] == 2
    assert repo.read_bytes("tree.svg") == exported
    repo.write("tree.svg", "foreign SVG bytes")
    assert run_cli(*args, "--replace")[0] == 0
    assert repo.read_bytes("tree.svg") == exported
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "options",
    [
        ("--format", "svg", "--output", "README.md", "--replace"),
        ("--format", "svg", "--output", "../tree.svg"),
        ("--format", "svg", "--output", "missing/tree.svg"),
        ("--format", "markdown", "--output", "new.md"),
        ("--format", "markdown", "--stdout", "--theme", "dark"),
        ("--format", "svg", "--stdout", "--replace"),
    ],
)
def test_invalid_export_does_not_write(repo, options):
    source = stamp(repo)
    original = source.read_bytes()
    code, output, error = run_cli("export", "--load", "README.md", *options)
    assert code == 2 and error and not output
    assert source.read_bytes() == original
    assert not (repo.path / "new.md").exists()


def test_loaded_svg_cannot_export_over_itself_and_manual_drawing_is_dirty(repo):
    source = stamp(repo)
    svg = repo.write("tree.svg", render_svg(parse_document(source.read_bytes())))
    original = svg.read_bytes()
    assert (
        run_cli(
            "export",
            "--load",
            "tree.svg",
            "--format",
            "svg",
            "--output",
            "tree.svg",
            "--replace",
        )[0]
        == 2
    )
    assert svg.read_bytes() == original
    svg.write_bytes(original.replace(b"Repository tree", b"Manual drawing"))
    assert run_cli("check", "tree.svg")[0] == 1
    assert b"Manual drawing" in svg.read_bytes()
    assert run_cli("update", "tree.svg")[0] == 0
    assert svg.read_bytes() == original
    assert run_cli("check", "tree.svg")[0] == 0


def test_new_tree_export_and_malformed_source(repo):
    repo.write("code.py")
    repo.add("code.py")
    code, output, error = run_cli("export", "--format", "svg", "--stdout")
    assert code == 0 and not error
    assert parse_svg(output.encode()).document.tree.children[0].name == "code.py"
    assert parse_svg(output.encode()).appearance.theme == "auto"
    bad = repo.write("bad.svg", "not SVG")
    assert (
        run_cli("export", "--load", "bad.svg", "--format", "markdown", "--stdout")[0]
        == 2
    )
    assert bad.read_text(encoding="utf-8") == "not SVG"


@pytest.mark.parametrize("missing_root", [False, True])
def test_svg_print_extracts_stored_tree_without_index_or_root_lookup(
    repo, monkeypatch, missing_root
):
    source = stamp(repo)
    document = parse_document(source.read_bytes())
    if missing_root:
        document = replace(
            document, settings=replace(document.settings, root="removed")
        )
    svg = repo.write("tree.svg", render_svg(document))
    original = svg.read_bytes()
    one, two = repo.blob(b"one"), repo.blob(b"two")
    repo.git_bytes(
        "update-index",
        "--index-info",
        input=f"100644 {one} 2\tunmerged\n100644 {two} 3\tunmerged\n".encode(),
    )

    def unexpected(*args, **kwargs):
        pytest.fail("SVG extraction must not capture a refreshed Git snapshot")

    monkeypatch.setattr("treestamp.cli_inputs.capture_snapshot", unexpected)
    code, output, error = run_cli("load", "tree.svg", "--print")
    assert code == 0 and not error
    assert parse_document(output.encode()) == document
    assert svg.read_bytes() == original


def test_svg_maintenance_guards_unmatched_notes_and_retains_appearance(repo):
    from tests.test_cli_notes import annotated

    source = annotated(repo, {"src/main.py": "keep this", "README.md": "retained"})
    document = parse_document(source.read_bytes())
    appearance = SvgAppearance(theme="dark")
    svg = repo.write("tree.svg", render_svg(document, appearance))
    original = svg.read_bytes()
    repo.git("rm", "src/main.py")
    code, output, error = run_cli("update", "tree.svg")
    assert code == 2 and not output and "1 unmatched" in error
    assert svg.read_bytes() == original
    code, output, error = run_cli("check", "tree.svg")
    assert code == 1 and output and "1 unmatched" in error
    assert svg.read_bytes() == original
    code, _, error = run_cli("update", "tree.svg", "--skip-notes-transfer")
    assert code == 0 and "1 unmatched" in error
    result = parse_svg(svg.read_bytes())
    assert result.appearance == appearance
    assert {
        node.path: node.annotation
        for node in result.document.tree.walk()
        if node.annotation
    } == {"README.md": "retained"}
    assert run_cli("check", "tree.svg")[0] == 0


def test_export_fresh_tree_uses_current_directory_as_root(repo, monkeypatch):
    repo.write("docs/leaf.txt")
    repo.write("outside.txt")
    repo.add(".")
    monkeypatch.chdir(repo.path / "docs")
    code, output, error = run_cli("export", "--format", "svg", "--stdout")
    assert code == 0 and not error
    document = parse_svg(output.encode()).document
    assert document.settings.root == "docs"
    assert {node.path for node in document.tree.walk()} == {"leaf.txt"}


def test_svg_load_opens_directly_and_preserves_pending_note_transfer(repo, monkeypatch):
    from tests.test_cli_notes import annotated

    source = annotated(repo, {"src/main.py": "keep this"})
    svg = repo.write(
        "tree.svg",
        render_svg(parse_document(source.read_bytes()), SvgAppearance(theme="dark")),
    )
    repo.git("rm", "src/main.py")
    opened = []
    monkeypatch.setattr(
        "treestamp.tui.explore", lambda editor: opened.append(editor) or False
    )
    assert run_cli("load", "tree.svg") == (0, "", "")
    assert len(opened) == 1
    state = opened[0].state
    assert state.document_path == svg
    assert state.source_format == "svg" and state.svg_appearance.theme == "dark"
    assert state.reconciliation.remaining == 1


def test_export_rejects_global_print_option(repo, capsys):
    from treestamp.cli import main

    stamp(repo)
    with pytest.raises(SystemExit) as caught:
        main(["--print", "export", "--format", "svg", "--stdout"])
    assert caught.value.code == 2
    output = capsys.readouterr()
    assert not output.out and "--stdout instead of --print" in output.err


@pytest.mark.parametrize(
    "arguments",
    [
        ["load", "tree.svg", "--print"],
        ["export", "--load", "tree.svg", "--format", "svg", "--stdout"],
    ],
)
def test_headless_svg_commands_do_not_import_textual(repo, arguments):
    import os
    import subprocess
    import sys
    from pathlib import Path

    source = stamp(repo)
    repo.write("tree.svg", render_svg(parse_document(source.read_bytes())))
    source_root = str(Path(__file__).resolve().parents[1] / "src")
    script = (
        "import sys; from treestamp.cli import main; "
        f"assert main({arguments!r}) == 0; "
        "assert not any(k == 'textual' or k.startswith('textual.') for k in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo.path,
        env={**os.environ, "PYTHONPATH": source_root},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("source_format", ["markdown", "svg"])
@pytest.mark.parametrize(
    "output", ["svg-stdout", "markdown-stdout", "new-file", "existing-file"]
)
def test_export_requires_note_transfer_before_emitting_or_writing(
    repo, source_format, output
):
    from tests.test_cli_notes import annotated

    source = annotated(repo, {"src/main.py": "do not lose this note"})
    if source_format == "svg":
        source = repo.write(
            "source.svg", render_svg(parse_document(source.read_bytes()))
        )
    original = source.read_bytes()
    repo.git("rm", "src/main.py")
    destination = repo.path / "copy.svg"
    if output == "existing-file":
        repo.write("copy.svg", "existing destination")
    if output.endswith("stdout"):
        args = ["--format", output.split("-")[0], "--stdout"]
    else:
        args = ["--format", "svg", "--output", "copy.svg"]
        if output == "existing-file":
            args.append("--replace")
    code, emitted, error = run_cli("export", "--load", source.name, *args)
    assert code == 2 and not emitted
    assert "unmatched notes" in error and "treestamp load DOCUMENT" in error
    assert source.read_bytes() == original
    if output == "existing-file":
        assert destination.read_text(encoding="utf-8") == "existing destination"
    else:
        assert not destination.exists()


@pytest.mark.parametrize("theme", ["auto", "light", "dark"])
def test_svg_export_retains_loaded_appearance_and_can_choose_automatic(repo, theme):
    source = stamp(repo)
    document = parse_document(source.read_bytes())
    svg = repo.write("tree.svg", render_svg(document, SvgAppearance(theme=theme)))
    original = svg.read_bytes()
    args = ("export", "--load", "tree.svg", "--format", "svg", "--stdout")
    code, output, error = run_cli(*args)
    assert code == 0 and not error
    assert parse_svg(output.encode()).appearance.theme == theme
    code, output, error = run_cli(*args, "--theme", "auto")
    assert code == 0 and not error
    assert parse_svg(output.encode()).appearance.theme == "auto"
    assert "@media (prefers-color-scheme: dark)" in output
    assert svg.read_bytes() == original
