"""Configuration normalization preserves document meaning and surrounding bytes."""

from pathlib import Path

import pytest

from treestamp.document import (
    Document,
    extract_region,
    load_document,
    parse_document,
    prepare_write,
    render_region,
)
from treestamp.model import Entry, Settings, build_tree
from treestamp.session import TreeSession


@pytest.mark.parametrize("eol", [b"\n", b"\r\n"])
@pytest.mark.parametrize("comment", ["# keep café".encode(), b"# legacy \xff"])
def test_config_normalization_preserves_meaning_and_surrounding_bytes(
    tmp_path: Path, eol: bytes, comment: bytes
) -> None:
    session = TreeSession(
        build_tree([Entry("byte\udcff  # name")]),
        Settings(root="sub", attribution=True),
    )
    session.set_annotation("byte\udcff  # name", "authored note")
    document = Document(
        session.printed_tree(),
        session.settings,
        hidden=frozenset({"sub/hidden\udcfe"}),
    )
    region = (
        render_region(document)
        .encode()
        .replace(
            b"<!-- treestamp:config\n", b"<!-- treestamp:config\n" + comment + b"\n"
        )
    )
    prefix, suffix = b"\xef\xbb\xbfIntro \x80\n", b"Outro \x81\n"
    original = (prefix + region + suffix).replace(b"\n", eol)
    path = tmp_path / "README.md"
    path.write_bytes(original)
    loaded, saved = load_document(path)
    assert loaded == document
    assert saved is not None

    prepared = prepare_write(loaded, path, expected=saved).content
    assert parse_document(prepared) == document
    assert prepared.startswith(prefix.replace(b"\n", eol))
    assert prepared.endswith(suffix.replace(b"\n", eol))
    exported = extract_region(prepared)
    exported.decode("utf-8")
    assert exported.count(eol) == exported.count(b"\n")
    if b"\xff" in comment:
        assert comment not in exported
    else:
        assert prepared == original
