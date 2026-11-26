"""Container-neutral source updates and isolated, conflict-checked exports."""

import stat
from dataclasses import replace

import pytest

from treestamp.artifacts import (
    Artifact,
    capture_export_destination,
    load_artifact,
    parse_artifact,
    prepare_artifact_content,
    prepare_artifact_write,
    prepare_svg_export,
)
from treestamp.document import Document, DocumentSnapshot, publish_write, render_region
from treestamp.errors import MarkerError
from treestamp.model import Entry, Settings, build_tree
from treestamp.svg import SvgAppearance, parse_svg, render_svg


def sample():
    return Document(build_tree([Entry("a -> b"), Entry("folder/readme.md")]))


@pytest.mark.parametrize("style", ["unicode", "ascii"])
def test_container_conversion_preserves_document(style):
    document = replace(sample(), settings=Settings(style=style))
    text = parse_artifact(render_region(document).encode())
    assert text.format == "markdown"
    svg = parse_artifact(
        render_svg(text.document, SvgAppearance(theme="dark")).encode()
    )
    assert svg.format == "svg" and svg.appearance.theme == "dark"
    assert render_region(svg.document) == render_region(text.document)


@pytest.mark.parametrize(
    "content", [b"<svg/>", b"<?xml malformed", b"<!DOCTYPE svg []><svg/>"]
)
def test_malformed_recognized_svg_never_becomes_absent(content):
    with pytest.raises(MarkerError):
        parse_artifact(content, allow_absent=True)
    with pytest.raises(MarkerError):
        parse_artifact(b"not SVG", location="bad.svg", allow_absent=True)
    assert parse_artifact(b"unmarked prose", allow_absent=True) is None


@pytest.mark.parametrize(
    "prefix",
    [
        b"<!-- edited externally -->\n",
        b"<?custom harmless?>\n",
        b"\xef\xbb\xbf<!-- comment -->\n<?custom harmless?>\n",
    ],
)
def test_svg_dispatch_accepts_inert_prolog_without_a_filename(prefix):
    content = prefix + render_svg(sample()).encode()
    assert parse_artifact(content).format == "svg"
    assert (
        parse_artifact(content, allow_absent=True).document
        == parse_svg(content).document
    )
    with pytest.raises(MarkerError):
        parse_artifact(prefix + b"<svg broken", allow_absent=True)


def test_optional_load_and_native_source_updates(repo):
    assert load_artifact(repo.path / "absent.md", allow_absent=True) == (None, None)
    plain = repo.write("unmarked.md", "prose")
    assert load_artifact(plain, allow_absent=True)[0] is None
    document = sample()
    for name, content in (
        ("tree.svg", render_svg(document)),
        ("README.md", "before\n" + render_region(document) + "after\n"),
    ):
        path = repo.write_bytes(name, content.encode())
        artifact, previous = load_artifact(path)
        candidate = replace(
            artifact, document=replace(document, settings=Settings(attribution=True))
        )
        prepared = prepare_artifact_write(
            candidate, path, expected=previous, repository=repo.path
        )
        assert prepared.content == prepare_artifact_content(candidate, previous.content)
        published = publish_write(prepared)
        assert parse_artifact(published.content).document.settings.attribution
        if name.endswith(".md"):
            assert published.content.startswith(
                b"before\n"
            ) and published.content.endswith(b"after\n")
        else:
            assert (
                prepare_artifact_content(candidate, published.content)
                == published.content
            )


@pytest.mark.parametrize("newline", [b"\n", b"\r\n"])
def test_svg_source_keeps_its_line_endings(repo, newline):
    """A checkout whose line endings Git converted is unchanged, and updates keep them."""
    content = render_svg(sample()).encode().replace(b"\n", newline)
    path = repo.write_bytes("tree.svg", content)
    artifact, previous = load_artifact(path)
    assert prepare_artifact_content(artifact, previous.content) == content
    candidate = replace(artifact, appearance=SvgAppearance(theme="dark"))
    published = publish_write(
        prepare_artifact_write(candidate, path, expected=previous, repository=repo.path)
    )
    lines = published.content.split(b"\n")[:-1]
    assert all(line.endswith(b"\r") == (newline == b"\r\n") for line in lines)
    assert parse_artifact(published.content).appearance == candidate.appearance


def test_source_update_refuses_external_changes_and_other_containers(repo):
    path = repo.write("tree.svg", render_svg(sample()))
    artifact, previous = load_artifact(path)
    path.write_text(
        render_svg(sample()).replace("Repository tree", "External drawing"),
        encoding="utf-8",
    )
    with pytest.raises(MarkerError, match="changed"):
        prepare_artifact_write(artifact, path, expected=previous)
    text = repo.write("README.md", render_region(sample()))
    with pytest.raises(MarkerError, match="loaded SVG"):
        prepare_artifact_write(artifact, text)
    with pytest.raises(MarkerError, match="unsupported artifact"):
        Artifact(sample(), "invalid")


def test_export_create_replace_and_both_races(repo):
    destination = repo.path / "tree.svg"
    assert capture_export_destination(destination, repository=repo.path) is None
    prepared = prepare_svg_export(sample(), destination, repository=repo.path)
    destination.write_text("appeared", encoding="utf-8")
    with pytest.raises(MarkerError, match="already exists"):
        publish_write(prepared)
    assert destination.read_text(encoding="utf-8") == "appeared"
    with pytest.raises(MarkerError, match="confirm replacement"):
        prepare_svg_export(sample(), destination, repository=repo.path)
    expected = capture_export_destination(destination, repository=repo.path)
    prepared = prepare_svg_export(
        sample(), destination, repository=repo.path, expected=expected
    )
    destination.write_text("changed after preparation", encoding="utf-8")
    with pytest.raises(MarkerError, match="changed after"):
        publish_write(prepared)
    with pytest.raises(MarkerError, match="destination changed"):
        prepare_svg_export(
            sample(), destination, repository=repo.path, expected=expected
        )
    expected = capture_export_destination(destination, repository=repo.path)
    destination.chmod(0o640)
    # Windows records only the read-only bit, so compare with what was stored.
    mode = stat.S_IMODE(destination.stat().st_mode)
    result = publish_write(
        prepare_svg_export(
            sample(), destination, repository=repo.path, expected=expected
        )
    )
    assert "a -> b" in [
        node.name for node in parse_svg(result.content).document.tree.walk()
    ]
    assert stat.S_IMODE(destination.stat().st_mode) == mode
    destination.unlink()
    result = publish_write(
        prepare_svg_export(sample(), destination, repository=repo.path)
    )
    assert result.content == render_svg(sample()).encode()


@pytest.mark.parametrize("target", ["README.md", "missing/tree.svg", "tree.svg"])
def test_export_validates_destination_before_writing(repo, target):
    source = repo.path / "tree.svg"
    with pytest.raises(MarkerError):
        prepare_svg_export(
            sample(), repo.path / target, repository=repo.path, source=source
        )
    assert not (repo.path / target).exists()


def test_export_boundary_links_and_confirmation_identity(repo):
    with pytest.raises(MarkerError, match="within the repository"):
        prepare_svg_export(
            sample(), repo.path.parent / "outside.svg", repository=repo.path
        )
    target = repo.write("existing.svg", "other SVG")
    link = repo.path / "link.svg"
    link.symlink_to(target)
    with pytest.raises(MarkerError, match="symbolic link"):
        capture_export_destination(link, repository=repo.path)
    with pytest.raises(MarkerError, match="destination changed"):
        prepare_svg_export(
            sample(),
            target,
            repository=repo.path,
            expected=DocumentSnapshot(repo.path / "different.svg", b"other SVG"),
        )
    nested = repo.path / "nested"
    nested.mkdir()
    (nested / ".git").mkdir()
    with pytest.raises(MarkerError, match="another repository"):
        capture_export_destination(nested / "tree.svg", repository=repo.path)


def test_export_publish_failure_preserves_original(repo, monkeypatch):
    destination = repo.write("old.svg", "preserve me")
    expected = capture_export_destination(destination, repository=repo.path)
    prepared = prepare_svg_export(
        sample(), destination, repository=repo.path, expected=expected
    )

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr("treestamp.document.os.replace", fail)
    with pytest.raises(OSError, match="disk failure"):
        publish_write(prepared)
    assert destination.read_text(encoding="utf-8") == "preserve me"
    assert not list(repo.path.glob(".treestamp-*"))


@pytest.mark.parametrize("alias_kind", ["hardlink", "case"])
def test_export_rejects_source_alias_even_with_replacement_confirmation(
    repo, alias_kind
):
    source = repo.write("Tree.svg", render_svg(sample()))
    original = source.read_bytes()
    alias = repo.path / ("copy.svg" if alias_kind == "hardlink" else "tree.svg")
    if alias_kind == "hardlink":
        alias.hardlink_to(source)
    elif not alias.exists():
        pytest.skip("filesystem is case-sensitive")
    # Windows paths compare case-insensitively, so compare the names.
    assert alias.name != source.name and alias.samefile(source)
    with pytest.raises(MarkerError, match="update the loaded source"):
        capture_export_destination(alias, repository=repo.path, source=source)
    with pytest.raises(MarkerError, match="update the loaded source"):
        prepare_svg_export(
            sample(),
            alias,
            repository=repo.path,
            source=source,
            expected=DocumentSnapshot(alias, original),
        )
    assert source.read_bytes() == original and alias.read_bytes() == original


def test_export_allows_distinct_case_names_on_case_sensitive_filesystems(repo):
    source = repo.write("Tree.svg", render_svg(sample()))
    destination = repo.path / "tree.svg"
    if destination.exists():
        pytest.skip("filesystem is case-insensitive")
    destination.write_text("distinct file", encoding="utf-8")
    original = source.read_bytes()
    previous = capture_export_destination(
        destination, repository=repo.path, source=source
    )
    published = publish_write(
        prepare_svg_export(
            sample(),
            destination,
            repository=repo.path,
            source=source,
            expected=previous,
        )
    )
    assert published.content == original
    assert not destination.samefile(source)
    assert source.read_bytes() == original


def test_export_identity_inspection_errors_fail_closed(repo, monkeypatch):
    source = repo.write("source.svg", render_svg(sample()))
    destination = repo.write("copy.svg", "preserve copy")
    original = source.read_bytes()

    def denied(*args):
        raise PermissionError("cannot inspect identity")

    monkeypatch.setattr(type(source), "samefile", denied)
    with pytest.raises(PermissionError, match="cannot inspect identity"):
        prepare_svg_export(
            sample(),
            destination,
            repository=repo.path,
            source=source,
            expected=DocumentSnapshot(destination, b"preserve copy"),
        )
    assert source.read_bytes() == original
    assert destination.read_text(encoding="utf-8") == "preserve copy"
