"""Document codecs and transactional boundaries with byte-level assertions."""

from dataclasses import replace
from pathlib import Path

import pytest

from treestamp.codec import parse_tree
from treestamp.document import (
    Document,
    load_document,
    normalized_hidden,
    parse_document,
    prepare_write,
    publish_write,
    render_interior,
    render_region,
    write_document,
)
from treestamp.errors import MarkerError
from treestamp.model import Entry, Settings, build_tree

START = b"<!-- treestamp:start -->"
END = b"<!-- treestamp:end -->"


@pytest.mark.parametrize("metadata", ["", '<!-- treestamp:config\nroot = "."\n-->\n'])
@pytest.mark.parametrize(
    "tree", [".  # note  \n", ".\n└── file  # note  \n", ".  #    \n"]
)
def test_unfenced_document_preserves_final_annotation_spaces(
    tmp_path: Path, metadata: str, tree: str
) -> None:
    path = tmp_path / "README.md"
    path.write_bytes(
        START + b"\n \t\n" + (metadata + tree).encode() + b"\n \t\n" + END + b"\n"
    )
    loaded, _ = load_document(path)
    assert loaded is not None
    assert loaded.tree == parse_tree(tree)
    write_document(loaded, path)
    assert load_document(path)[0] == loaded


@pytest.fixture
def document() -> Document:
    return Document(build_tree([Entry("src/main.py"), Entry("README.md")]), Settings())


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_create_load_and_update_round_trip(
    document: Document, tmp_path: Path, style: str
) -> None:
    document = replace(document, settings=replace(document.settings, style=style))
    path = tmp_path / "README.md"
    saved = write_document(document, path, create=True)
    loaded, snapshot = load_document(path)
    assert loaded == document
    assert snapshot == saved
    prepared = prepare_write(loaded, path, expected=snapshot)
    assert prepared.content == saved.content


@pytest.mark.parametrize("path_name", ["🌲.txt", "name\x7f.txt", "<🌲>.txt"])
def test_unicode_and_escaped_metadata_round_trip(
    document: Document, tmp_path: Path, path_name: str
) -> None:
    root = tmp_path / path_name
    path = tmp_path / "README.md"
    source = replace(
        document,
        settings=replace(document.settings, root=root.name),
        hidden=frozenset({path_name + "/hidden"}),
    )
    write_document(source, path, create=True)
    loaded, snapshot = load_document(path)
    assert loaded == source
    assert snapshot
    assert prepare_write(loaded, path, expected=snapshot).content == snapshot.content


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_annotation_normalization_survives_document_save_and_load(
    document: Document, tmp_path: Path, style: str
) -> None:
    source = replace(
        document,
        settings=replace(document.settings, style=style),
        tree=replace(document.tree, annotation=' "literal\\n"\ttext \t'),
    )
    path = tmp_path / "README.md"
    saved = write_document(source, path, create=True)
    loaded, snapshot = load_document(path)
    assert loaded is not None
    assert loaded.tree.annotation == ' "literal\\n"  text   '
    assert prepare_write(loaded, path, expected=snapshot).content == saved.content
    invalid = replace(source, tree=replace(source.tree, annotation="two\nlines"))
    with pytest.raises(MarkerError, match="single line"):
        write_document(invalid, path)
    assert path.read_bytes() == saved.content


@pytest.mark.parametrize(
    "interior",
    [
        b"",
        b"old prose\n",
        b"<!-- treestamp:config\nmalformed = [\n",
        b"```text\nunclosed\n",
    ],
)
def test_write_does_not_read_old_tree_or_settings(
    document: Document, tmp_path: Path, interior: bytes
) -> None:
    path = tmp_path / "README.md"
    before = b"Intro\r\n" + START + b"\r\n" + interior + END + b"\r\nOutro"
    path.write_bytes(before)
    result = write_document(document, path)
    assert result.content.startswith(b"Intro\r\n" + START + b"\r\n")
    assert result.content.endswith(END + b"\r\nOutro")
    assert b"\n" not in result.content.replace(b"\r\n", b"")
    assert load_document(path)[0] == document


@pytest.mark.parametrize(
    "contents",
    [
        b"ordinary prose",
        START,
        END,
        END + b"\n" + START,
        START + b"\n" + START + b"\n" + END,
        START + b"\n" + END + b"\n" + END,
        b"<!-- treestamp:start x -->\n" + END,
    ],
)
def test_invalid_markers_never_write(
    document: Document, tmp_path: Path, contents: bytes
) -> None:
    path = tmp_path / "README.md"
    path.write_bytes(contents)
    with pytest.raises(MarkerError):
        write_document(document, path)
    assert path.read_bytes() == contents


@pytest.mark.parametrize("indent", [b" ", b"  ", b"   ", b"    ", b"\t", b" \t"])
@pytest.mark.parametrize("markers", [(START,), (END,), (START, END)])
def test_indented_boundaries_are_rejected_without_rewriting(
    document: Document, tmp_path: Path, indent: bytes, markers: tuple[bytes, ...]
) -> None:
    path = tmp_path / "README.md"
    original = render_region(document).encode()
    for marker in markers:
        original = original.replace(marker, indent + marker)
    path.write_bytes(original)
    with pytest.raises(MarkerError, match="boundary markers must not be indented"):
        load_document(path)
    with pytest.raises(MarkerError, match="boundary markers must not be indented"):
        write_document(document, path)
    assert path.read_bytes() == original


@pytest.mark.parametrize("indent", [b"", b"  ", b"\t"])
def test_fenced_examples_and_outside_bytes_survive(
    document: Document, tmp_path: Path, indent: bytes
) -> None:
    path = tmp_path / "README.md"
    example = b"```html\n" + indent + START + b"\n" + indent + END + b"\n```\n"
    path.write_bytes(example + START + b"\n" + END + b"\n" + example)
    saved = write_document(document, path)
    assert saved.content.startswith(example) and saved.content.endswith(example)


def test_create_no_clobber_and_both_conflict_windows(
    document: Document, tmp_path: Path
) -> None:
    path = tmp_path / "README.md"
    saved = write_document(document, path, create=True)
    with pytest.raises(MarkerError):
        write_document(document, path, create=True)
    prepared = prepare_write(document, path, expected=saved)
    path.write_bytes(b"changed externally")
    with pytest.raises(MarkerError):
        publish_write(prepared)
    with pytest.raises(MarkerError):
        prepare_write(document, path, expected=saved)
    assert path.read_bytes() == b"changed externally"


def test_failed_atomic_replace_preserves_document(
    document: Document, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "README.md"
    saved = write_document(document, path, create=True)
    prepared = prepare_write(document, path)

    def fail(*args: object) -> None:
        raise OSError("injected failure")

    monkeypatch.setattr("treestamp.document.os.replace", fail)
    with pytest.raises(OSError):
        publish_write(prepared)
    assert path.read_bytes() == saved.content
    assert not list(tmp_path.glob(".treestamp-*"))


def test_metadata_free_input_uses_defaults(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_bytes(START + "\n```text\n.\n└── src/\n```\n".encode() + END + b"\n")
    document, _ = load_document(path)
    assert document is not None
    assert document.settings == Settings(show_counts=False)
    assert document.tree.children[0].path == "src"


def test_hiding_under_collapsed_parents_are_not_persisted(
    document: Document,
) -> None:
    src = replace(document.tree.children[0], children=())
    root = replace(document.tree, children=(src,))
    assert normalized_hidden(
        Document(root, hidden=frozenset({"README.md", "src/main.py"}))
    ) == frozenset({"README.md"})


@pytest.mark.parametrize(
    "payload",
    [
        "unknown = true",
        "max_children = 0",
        'hidden = ["../escape"]',
        'hidden = "a"',
        "show_counts = 1",
        "root = 2",
        "depth = true",
    ],
)
def test_invalid_metadata_fails(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "README.md"
    path.write_text(
        "<!-- treestamp:start -->\n<!-- treestamp:config\n"
        + payload
        + "\n-->\n.\n<!-- treestamp:end -->\n"
    )
    with pytest.raises(MarkerError):
        load_document(path)


def test_byte_paths_in_metadata_round_trip(document: Document, tmp_path: Path) -> None:
    root = tmp_path / "project\udcff"
    path = tmp_path / "README.md"
    source = replace(
        document,
        settings=replace(document.settings, root=root.name),
        hidden=frozenset({root.name + "/bad\udcff", root.name + "/literal\\udcff"}),
    )
    write_document(source, path, create=True)
    loaded, _ = load_document(path)
    assert loaded == source
    assert "git_bytes" in path.read_text()


def test_deep_input_fails_explicitly_before_rendering() -> None:
    from treestamp.codec import parse_tree
    from treestamp.model import MAX_DEPTH

    text = ".\n" + "\n".join(
        "    " * depth + "└── a/" for depth in range(MAX_DEPTH + 1)
    )
    with pytest.raises(MarkerError, match="depth limit"):
        parse_tree(text)


def test_list_inline_root_is_not_mistaken_for_fence(
    document: Document, tmp_path: Path
) -> None:
    tree = replace(document.tree, annotation="``literal``")
    source = replace(document, tree=tree, settings=Settings(style="list"))
    path = tmp_path / "README.md"
    write_document(source, path, create=True)
    assert load_document(path)[0] == source


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_render_region_matches_created_file_bytes(
    document: Document, tmp_path: Path, style: str
) -> None:
    document = replace(document, settings=replace(document.settings, style=style))
    prepared = prepare_write(document, tmp_path / "README.md", create=True)
    assert render_region(document, ".").encode() == prepared.content
    assert parse_document(prepared.content) == document
    nested = prepare_write(document, tmp_path / "docs" / "README.md", create=True)
    assert render_region(document).encode() == nested.content


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_region_carries_no_blank_lines(document: Document, style: str) -> None:
    document = replace(document, settings=replace(document.settings, style=style))
    region = render_region(document, ".")
    assert region.endswith("\n")
    assert "" not in region[:-1].split("\n")


def test_parse_document_round_trips_byte_paths(document: Document) -> None:
    document = replace(document, hidden=frozenset({"src/\udcff.bin"}))
    content = render_region(document, ".").encode("utf-8", "surrogateescape")
    assert b"git_bytes" in content
    assert parse_document(content) == document


@pytest.mark.parametrize("root", ["src/", "./src", "a//b", "", "src/..", "../src"])
def test_render_interior_rejects_unnormalized_root(
    document: Document, root: str
) -> None:
    with pytest.raises(MarkerError, match="root|path"):
        render_interior(document, root)


@pytest.mark.parametrize("root", [".", "src", "src/sub"])
def test_render_interior_accepts_normalized_root(document: Document, root: str) -> None:
    loaded = parse_document(render_region(document, root).encode())
    assert loaded.settings.root == root


def test_parse_document_matches_file_based_errors(tmp_path: Path) -> None:
    assert parse_document(START + b"\r\n.\r\n" + END + b"\r\n").tree.children == ()
    cases = [
        (b"no markers", "no treestamp marker pair"),
        (START + b"\n.\n", "missing end marker"),
        (START + b"\n" + START + b"\n" + END + b"\n", "duplicate or nested"),
        (b"<!-- treestamp:start extra -->\n", "malformed treestamp boundary"),
    ]
    for content, message in cases:
        with pytest.raises(MarkerError, match=message) as memory:
            parse_document(content, location="memo")
        assert str(memory.value).startswith("memo: ")
        path = tmp_path / "README.md"
        path.write_bytes(content)
        with pytest.raises(MarkerError, match=message):
            load_document(path)


def test_prepare_content_matches_prepare_write_and_keeps_line_endings(
    document: Document, tmp_path: Path
) -> None:
    from treestamp.document import prepare_content

    path = tmp_path / "README.md"
    path.write_bytes(
        b"# Title\r\n\r\n" + START + b"\r\nold\r\n" + END + b"\r\n\r\ntail\r\n"
    )
    prepared = prepare_write(document, path)
    assert prepare_content(document, ".", path.read_bytes()) == prepared.content
    assert b"\r\n```sh\r\n" in prepared.content and prepared.content.endswith(
        b"tail\r\n"
    )
    assert parse_document(prepared.content, allow_absent=True) is not None
    assert parse_document(b"plain prose\n", allow_absent=True) is None
    with pytest.raises(MarkerError, match="tree is empty"):
        parse_document(START + b"\n \t\n" + END, allow_absent=True)
    with pytest.raises(MarkerError, match="no treestamp marker pair"):
        prepare_content(document, ".", b"plain prose\n", location="memo")
    with pytest.raises(MarkerError, match="malformed"):
        parse_document(b"<!-- treestamp:start extra -->\n", allow_absent=True)


def test_default_document_has_no_config_noise(document: Document) -> None:
    region = render_region(document, ".")
    assert "treestamp:config" not in region
    assert parse_document(region.encode()) == document


@pytest.mark.parametrize("ending", [b"\n", b"\r\n"])
def test_unrepresentable_output_preserves_the_entire_existing_document(
    tmp_path: Path, ending: bytes
) -> None:
    path = tmp_path / "README.md"
    before = ending.join(
        [b"\xef\xbb\xbf# Intro  ", START, b"./", END, b"unrelated\xff bytes", b""]
    )
    path.write_bytes(before)
    document = Document(build_tree([Entry("odd -> name")]))
    with pytest.raises(MarkerError, match="cannot represent"):
        write_document(document, path)
    assert path.read_bytes() == before
    assert not list(tmp_path.glob(".treestamp-*"))


def test_optional_parse_rejects_malformed_content_instead_of_treating_it_as_absent() -> (
    None
):
    with pytest.raises(MarkerError):
        parse_document(START + b"\ninvalid tree\n" + END, allow_absent=True)


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_config_is_only_curation_and_minimal_special_identities(style: str) -> None:
    source = Document(
        build_tree(
            [Entry("notes  # drafts/ordinary"), Entry("notes  # drafts/a  # b")]
        ),
        Settings(root="src", style=style),
        frozenset({"src/hidden"}),
    )
    region = render_region(source)
    assert 'root = "src"' in region
    assert 'hidden = ["src/hidden"]' in region
    assert (
        'special_paths = ["src/notes  # drafts", "src/notes  # drafts/a  # b"]'
        in region
    )
    assert "style =" not in region and "show_counts =" not in region
    assert parse_document(region.encode()) == source


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_root_only_style_and_count_inference(style: str) -> None:
    from treestamp.model import Node

    document = Document(Node(".", "", "dir"), Settings(style=style, show_counts=False))
    loaded = parse_document(render_region(document).encode())
    assert loaded.settings.style == ("list" if style == "list" else "unicode")
    assert loaded.settings.show_counts is True


def test_count_visibility_inferred_without_config() -> None:
    from treestamp.model import Node

    for count, shown in [(None, False), (3, True)]:
        tree = Node(".", "", "dir", children=(Node("dir", "dir", "dir", files=count),))
        loaded = parse_document(render_region(Document(tree)).encode())
        assert loaded.settings.show_counts is shown
    with pytest.raises(MarkerError, match="consistent count visibility"):
        parse_document(START + b"\n./\n- a/ (2 files)\n- b/\n" + END)


@pytest.mark.parametrize(
    "payload",
    [
        'hidden = ["src"]',
        'hidden = ["elsewhere/a"]',
        'hidden = ["src/a", "src/a"]',
        'special_paths = ["src/ordinary"]',
        'special_paths = ["src/a  # b"]',
        "special_paths = 3",
        'special_paths = ["src/a  # b", "src/a  # b"]',
        'root = "src"\nroot = "src"',
        'hidden = [{git_bytes = "invalid"}]',
    ],
)
def test_invalid_metadata_never_reconstructs_another_identity(payload: str) -> None:
    content = f'{START.decode()}\n<!-- treestamp:config\nroot = "src"\n{payload}\n-->\n```sh\n./\n```\n{END.decode()}\n'
    with pytest.raises(MarkerError):
        parse_document(content.encode())


def test_hidden_cannot_overlap_printed_rows_or_live_under_a_collapsed_directory() -> (
    None
):
    for hidden in ["src", "src/child"]:
        content = f'{START.decode()}\n<!-- treestamp:config\nhidden = ["{hidden}"]\n-->\n```sh\n./\n└── src/\n```\n{END.decode()}\n'
        with pytest.raises(MarkerError, match="hidden|printed"):
            parse_document(content.encode())


def test_region_extraction_preserves_original_framing_and_endings() -> None:
    from treestamp.document import extract_region

    region = START + b"\r\n```sh\r\n./\r\n```\r\n" + END + b"\r\n"
    assert extract_region(b"# Before\r\n" + region + b"After\r\n") == region
    assert extract_region(region.rstrip(b"\r\n")) == region.rstrip(b"\r\n")
    with pytest.raises(MarkerError, match="no treestamp"):
        extract_region(b"ordinary document")


def test_byte_special_paths_roundtrip_without_redundant_descendants() -> None:
    source = Document(
        build_tree(
            [Entry("bad\udcff  # dir/plain"), Entry("bad\udcff  # dir/child  # name")]
        )
    )
    content = render_region(source).encode()
    assert b"git_bytes" in content
    assert parse_document(content) == source
    assert b"/plain" not in content
