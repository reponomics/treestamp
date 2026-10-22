import pytest

from treestamp_web.links import (
    LinkError,
    ParsedLink,
    Repository,
    parse_link,
    repository,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("pallets/flask", Repository("pallets", "flask")),
        ("  pallets/flask  ", Repository("pallets", "flask")),
        ("github.com/pallets/flask", Repository("pallets", "flask")),
        ("https://github.com/pallets/flask", Repository("pallets", "flask")),
        ("http://www.github.com/pallets/flask/", Repository("pallets", "flask")),
        ("https://github.com/pallets/flask.git", Repository("pallets", "flask")),
        ("https://github.com/pallets/flask#readme", Repository("pallets", "flask")),
        (
            "https://github.com/pallets/flask?tab=readme-ov-file",
            Repository("pallets", "flask"),
        ),
        (
            "https://github.com/a-b/c.d_e/tree/" + "a" * 40,
            Repository("a-b", "c.d_e", "a" * 40),
        ),
    ],
)
def test_accepted_links(text: str, expected: Repository) -> None:
    assert parse_link(text) == ParsedLink(expected)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "flask",
        "https://gitlab.com/pallets/flask",
        "https://github.com/pallets",
        "https://github.com/-pallets/flask",
        "https://github.com/pallets/..",
        "https://github.com/pallets/fl ask",
        "x" * 3000,
    ],
)
def test_rejected_links(text: str) -> None:
    with pytest.raises(LinkError):
        parse_link(text)


@pytest.mark.parametrize(
    ("text", "ref"),
    [
        ("https://github.com/pallets/flask/tree/main", "main"),
        ("https://github.com/pallets/flask/tree/feature/x/", "feature/x"),
        ("https://github.com/pallets/flask/tree/v2.0.0", "v2.0.0"),
    ],
)
def test_named_refs_only_with_allow_refs(text: str, ref: str) -> None:
    lenient = parse_link(text)
    assert lenient.repository == Repository("pallets", "flask")
    assert lenient.ignored == f"tree/{ref}"
    assert "ignored" in (lenient.notice or "") and "default branch" in (
        lenient.notice or ""
    )
    assert parse_link(text, allow_refs=True) == ParsedLink(
        Repository("pallets", "flask", ref)
    )


@pytest.mark.parametrize(
    ("text", "ignored", "hint"),
    [
        (
            "https://github.com/pallets/flask/blob/main/README.md",
            "blob/main/README.md",
            "set Document to it",
        ),
        (
            "https://github.com/pallets/flask/blob/main/src/app.py",
            "blob/main/src/app.py",
            None,
        ),
        ("https://github.com/pallets/flask/pull/1", "pull/1", None),
        ("https://github.com/pallets/flask/tree/", "tree", None),
        ("https://github.com/pallets/flask/tree/a b", "tree/a b", None),
        (
            "https://github.com/pallets/flask/tree/" + "x" * 300,
            "tree/" + "x" * 300,
            None,
        ),
    ],
)
def test_other_segments_are_ignored_with_a_notice(
    text: str, ignored: str | None, hint: str | None
) -> None:
    parsed = parse_link(text)
    assert parsed.repository == Repository("pallets", "flask")
    assert parsed.ignored == ignored
    if hint:
        assert hint in (parsed.notice or "")
    elif ignored:
        assert "set Document" not in (parsed.notice or "")


def test_commit_segments_pin() -> None:
    sha = "a" * 40
    assert parse_link(f"https://github.com/o/r/commit/{sha}") == ParsedLink(
        Repository("o", "r", sha)
    )
    assert parse_link(f"https://github.com/o/r/tree/{sha}/") == ParsedLink(
        Repository("o", "r", sha)
    )


def test_components_and_pinned() -> None:
    assert repository("o", "r", "HEAD") == Repository("o", "r", "HEAD")
    assert not repository("o", "r", "main").pinned
    assert repository("o", "r", "0" * 40).pinned
    assert Repository("o", "r").url == "https://github.com/o/r"
    with pytest.raises(LinkError, match="owner"):
        repository("", "r")
    with pytest.raises(LinkError, match="name"):
        repository("o", ".")
    with pytest.raises(LinkError, match="ref"):
        repository("o", "r", "a@{1}")
