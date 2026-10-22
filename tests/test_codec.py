"""Printed trees preserve authored data independently of Git."""

from dataclasses import replace

import pytest

from treestamp.codec import parse_tree, render_tree, special_paths
from treestamp.errors import MarkerError
from treestamp.model import Entry, Node, Settings, build_tree, initial_tree


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_codec_roundtrip_all_kinds_counts_and_escaping(style: str) -> None:
    tree = Node(
        ".",
        "",
        "dir",
        children=(
            Node(
                "folder",
                "folder",
                "dir",
                files=None,
                dirs=2,
                annotation='a # (5 files) "note"',
            ),
            Node(
                "expanded",
                "expanded",
                "dir",
                children=(
                    Node("a b", "expanded/a b", "file", annotation="plain note"),
                    Node("link", "expanded/link", "symlink", target='../../a "b"\n'),
                    Node("module", "expanded/module", "gitlink"),
                ),
            ),
            Node("odd\\\t\n#name", "odd\\\t\n#name", "file"),
            Node("bad\udcffbyte", "bad\udcffbyte", "file"),
        ),
        annotation="root note",
    )
    printed = render_tree(tree, Settings(style=style))
    assert parse_tree(printed) == tree
    assert parse_tree(printed, style) == tree
    assert render_tree(parse_tree(printed), Settings(style=style)) == printed


def test_simple_manual_tree_and_annotation() -> None:
    tree = parse_tree(
        ".\n├── src/\n│   └── main.py  # Entry point\n└── tests/ (4 files)\n"
    )
    assert tree.children[0].children[0].annotation == "Entry point"
    assert tree.children[1].files == 4
    assert tree.children[1].dirs is None


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
@pytest.mark.parametrize(
    "annotation,expected",
    [
        ("Design and integration recipes", "Design and integration recipes"),
        ("Trees 🌲", "Trees 🌲"),
        ('Contains "quotes" # (5 files)', 'Contains "quotes" # (5 files)'),
        (r"Literal \n", r"Literal \n"),
        ('"Quoted" note', '"Quoted" note'),
        ('"Unclosed quote', '"Unclosed quote'),
        ("two\tcolumns", "two  columns"),
        (" padded \t", " padded   "),
    ],
)
def test_annotation_prints_literal_text_with_normalized_whitespace(
    style: str, annotation: str, expected: str
) -> None:
    tree = Node(
        ".",
        "",
        "dir",
        annotation=annotation,
        children=(Node("docs", "docs", "dir", annotation=annotation),),
    )
    printed = render_tree(tree, Settings(style=style))
    assert f"./  # {expected}" in printed
    assert f"docs/  # {expected}" in printed
    normalized = replace(
        tree,
        annotation=expected,
        children=(replace(tree.children[0], annotation=expected),),
    )
    assert parse_tree(printed) == normalized
    assert render_tree(normalized, Settings(style=style)) == printed


@pytest.mark.parametrize(
    "annotation",
    ["two\nlines", "trailing\n", "two\rlines", "two\u2028lines", "bad\x00text"],
)
def test_invalid_annotations_are_rejected_instead_of_escaped(annotation: str) -> None:
    with pytest.raises(MarkerError, match="single line"):
        render_tree(Node(".", "", "dir", annotation=annotation), Settings())


def test_parse_annotations_preserves_literal_quotes_and_normalizes_whitespace() -> None:
    tree = parse_tree('.\n- a  # "literal\\n"\ttext \t\n')
    assert tree.children[0].annotation == '"literal\\n"  text   '


def test_whitespace_only_annotation_is_preserved() -> None:
    tree = Node(".", "", "dir", annotation=" \t ")
    printed = render_tree(tree, Settings())
    assert printed == "./  #     \n"
    assert parse_tree(printed).annotation == "    "


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not-root\n",
        ".\n  - skipped\n",
        ".\n- a\n  - b\n",
        ".\n- a\n- a\n",
        ".\n- ../\n",
        '.\n- "a/b"\n',
        ".\n- a/ (-1 files)\n",
        ".\n- a/ (1 file)\n  - b\n",
        ". (2 files)\n",
        ".\n- a/ [gitlink]\n",
        ".\n- a/ (2 folders, 3 folders)\n",
        ".\n- /\n",
        ".\n- a\n\n",
    ],
)
def test_invalid_printed_trees_fail(text: str) -> None:
    with pytest.raises(MarkerError):
        parse_tree(text)


def test_unknown_style_fails() -> None:
    with pytest.raises(MarkerError):
        parse_tree(".\n", "invented")


def test_null_symlink_target_and_directory_count_roundtrip() -> None:
    text = ".\n- dir/ (4 folders)\n- link -> null\n"
    printed = render_tree(parse_tree(text), Settings(style="list"))
    assert printed == "./\n- dir/ (4 folders)\n- link -> null\n"
    assert parse_tree(printed) == parse_tree(text)


@pytest.mark.parametrize(
    "paths", [["a", "a"], ["a", "a/b"], ["../a"], ["/a"], ["a//b"], ["a\x00"]]
)
def test_source_paths_reject_ambiguity(paths: list[str]) -> None:
    with pytest.raises(MarkerError):
        build_tree(Entry(path) for path in paths)


def test_initial_layout_counts_immediate_children_and_allows_root_overflow() -> None:
    target = build_tree(
        [Entry("z"), Entry("b/link", "symlink", "x"), Entry("b/sub/x"), Entry("a")]
    )
    result = initial_tree(target, Settings())
    assert [child.path for child in result.children] == ["b", "a", "z"]
    assert result.children[0].files == 1
    assert result.children[0].dirs == 1
    assert result.children[0].children == ()
    assert target.children[0].children


@pytest.mark.parametrize(
    "kwargs",
    [
        {"style": "other"},
        {"show_counts": 1},
        {"root": "/absolute"},
        {"root": ""},
    ],
)
def test_invalid_settings(kwargs: dict[str, object]) -> None:
    with pytest.raises(MarkerError):
        Settings(**kwargs)  # type: ignore[arg-type]


def test_build_rejects_explicit_empty_directory() -> None:
    with pytest.raises(MarkerError):
        build_tree([Entry("empty", "dir")])


def test_invalid_node_facts_cannot_be_rendered() -> None:
    root = build_tree([Entry("a")])
    for bad in [
        replace(root.children[0], kind="unknown"),
        replace(root.children[0], annotation=12),
        replace(root.children[0], target="invalid"),
        replace(root.children[0], files=-2),
        replace(root.children[0], name="other"),
        replace(root.children[0], path="unexpected"),
    ]:
        with pytest.raises(MarkerError):
            render_tree(replace(root, children=(bad,)), Settings())


@pytest.mark.parametrize("field", ["root", "style"])
@pytest.mark.parametrize("value", [2, None, [], {}])
def test_settings_reject_invalid_runtime_types(field: str, value: object) -> None:
    with pytest.raises(MarkerError):
        Settings(**{field: value})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "name",
    [
        "a,b",
        "hash # annotation",
        "(3 files)",
        " a ",
        'a"b',
        "emoji🌲",
        "back\\slash",
        "line\r\nbreak",
        "tab\tname",
        "- child",
    ],
)
@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_special_names_and_annotations_cannot_become_tree_syntax(
    name: str, style: str
) -> None:
    root = build_tree([Entry(name)])
    child = replace(
        root.children[0], annotation=f"Comment about {name!r}; # a,b (3 folders)"
    )
    expected = replace(root, children=(child,))
    settings = Settings(style=style)
    assert (
        parse_tree(
            render_tree(expected, settings),
            special_paths=special_paths(expected),
        )
        == expected
    )


def test_indentation_cannot_skip_multiple_levels() -> None:
    with pytest.raises(MarkerError, match="skips a parent"):
        parse_tree(".\n- a/\n    - missing-parent\n")


def test_model_rejects_invalid_root_duplicate_nodes_and_leaf_children() -> None:
    root = build_tree([Entry("a")])
    child = root.children[0]
    invalid_trees = [
        child,
        replace(root, path="invalid-root"),
        replace(root, children=(child, child)),
        replace(root, children=(replace(child, children=(child,)),)),
    ]
    for tree in invalid_trees:
        with pytest.raises(MarkerError):
            render_tree(tree, Settings())


def test_invalid_symlink_target_type_is_rejected_before_serialization() -> None:
    root = Node(".", "", "dir", children=(Node("link", "link", "symlink", target=42),))  # type: ignore[arg-type]
    with pytest.raises(MarkerError):
        render_tree(root, Settings())


def test_unencodable_path_fails_explicitly() -> None:
    with pytest.raises(MarkerError):
        build_tree([Entry("bad\ud800")])


@pytest.mark.parametrize(
    "name",
    [
        "[report](url)",
        "![image](url)",
        "**bold**",
        "_emphasis_",
        "<img src=x onerror=alert(1)>",
        "&copy;",
        "a`b",
        "a``b",
        "a```b",
    ],
)
def test_list_names_render_as_themselves(name: str) -> None:
    """A name is data from someone's repository and must read as written."""
    from markdown_it import MarkdownIt

    tree = replace(build_tree([Entry(name)]), children=(Node(name, name, "file"),))
    printed = render_tree(tree, Settings(style="list"))
    assert parse_tree(printed) == tree
    html = MarkdownIt("commonmark", {"html": True}).render(printed)
    for construct in ("<a ", "<img ", "<strong>", "<em>", "&copy;"):
        assert construct not in html, (name, html)


def test_list_annotations_are_the_maintainers_markdown() -> None:
    """The opposite guarantee: an annotation is prose, and renders as prose."""
    from markdown_it import MarkdownIt

    annotation = "see [the design](d.md), **note** the `codec`"
    tree = replace(
        build_tree([Entry("docs/guide.md")]),
        children=(Node("docs", "docs", "dir", annotation=annotation),),
    )
    printed = render_tree(tree, Settings(style="list"))
    assert printed == f"./\n- docs/  # {annotation}\n"
    assert parse_tree(printed) == tree
    html = MarkdownIt("commonmark", {"html": True}).render(printed)
    assert '<a href="d.md">the design</a>' in html
    assert "<strong>note</strong>" in html and "<code>codec</code>" in html


def test_list_rows_escape_names_and_targets_and_leave_structure_plain() -> None:
    from markdown_it import MarkdownIt

    tree = parse_tree(
        ".\n- collapsed/ (3 files, 2 folders)  # count `note`\n- expanded/\n  - link -> a`b  # <b>link</b>\n"
    )
    printed = render_tree(tree, Settings(style="list"))
    assert parse_tree(printed) == tree
    # Counts, the arrow, and the marker are the format's own text and need no
    # protection; the target's backtick is escaped so the page shows it as is.
    assert "- collapsed/ (3 files, 2 folders)  # count `note`" in printed
    assert "- link -> a\\`b  # <b>link</b>" in printed
    html = MarkdownIt("commonmark", {"html": True}).render(printed)
    assert "<b>link</b>" in html  # the annotation is the maintainer's Markdown
    assert "<code>note</code>" in html
    assert "a`b" in html


def test_list_root_annotation_stays_live_markdown() -> None:
    tree = Node(".", "", "dir", annotation="[root](url)")
    printed = render_tree(tree, Settings(style="list"))
    assert printed == "./  # [root](url)\n"
    assert parse_tree(printed, "list") == tree


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
@pytest.mark.parametrize(
    "name", ["name #", "name # ", "name ##", "name   ", "name\u00a0"]
)
def test_marker_protects_filename_boundaries_without_an_annotation(
    style: str, name: str
) -> None:
    tree = build_tree([Entry(name)])
    settings = Settings(style=style)
    printed = render_tree(tree, settings)
    trimmed = "\n".join(line.rstrip() for line in printed.splitlines()) + "\n"
    assert printed == trimmed
    assert parse_tree(trimmed, style, special_paths=special_paths(tree)) == tree


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_ordinary_names_need_no_quotes_or_extra_marker(style: str) -> None:
    names = [
        "let's try this.md",
        "my café.md",
        "Screenshot (1).png",
        "notes #1.md",
        "report (3 files)",
    ]
    tree = build_tree(Entry(name) for name in names)
    settings = Settings(style=style)
    printed = render_tree(tree, settings)
    assert special_paths(tree) == frozenset()
    for name in names:
        assert name in printed
    assert parse_tree(printed, style) == tree


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_control_characters_and_literal_escapes_remain_distinct(style: str) -> None:
    names = [
        "a\nb",
        r"a\nb",
        "a\x85b",
        r"a\u0085b",
        "a\u2028b",
        "a\u2029b",
        "raw\udcff",
        r"raw\xff",
    ]
    tree = build_tree(Entry(name) for name in names)
    printed = render_tree(tree, Settings(style=style))
    assert len(printed.splitlines()) == len(names) + 1
    assert parse_tree(printed, style) == tree
    assert printed.encode("utf-8")


@pytest.mark.parametrize("text", ["./\n└── literal\\q.txt\n", "./\n- literal\\q.txt\n"])
def test_unknown_escapes_do_not_delete_filename_characters(text: str) -> None:
    assert parse_tree(text).children[0].name == r"literal\q.txt"


@pytest.mark.parametrize("style", ["unicode", "ascii"])
@pytest.mark.parametrize("name", ["odd -> name", "vendor [gitlink]"])
def test_ambiguous_rows_are_refused_instead_of_silently_changing_identity(
    style: str, name: str
) -> None:
    with pytest.raises(MarkerError, match="cannot represent"):
        render_tree(build_tree([Entry(name)]), Settings(style=style))


def test_list_escaping_can_disambiguate_names_without_a_blacklist() -> None:
    tree = build_tree([Entry("odd -> name"), Entry("vendor [gitlink]")])
    printed = render_tree(tree, Settings(style="list"))
    assert parse_tree(printed, "list") == tree


@pytest.mark.parametrize("style", ["unicode", "ascii"])
def test_fixed_fence_preserves_backticks_in_names_and_annotations(style: str) -> None:
    from markdown_it import MarkdownIt

    tree = Node(
        ".",
        "",
        "dir",
        annotation="``````",
        children=(
            Node("```", "```", "file", annotation="```"),
            Node("dir", "dir", "dir", children=(Node("``````", "dir/``````", "file"),)),
        ),
    )
    settings = Settings(style=style)
    body = render_tree(tree, settings)
    framed = render_tree(tree, settings, fenced=True)
    assert framed == "```sh\n" + body + "```\n"
    blocks = MarkdownIt().parse(framed)
    assert len(blocks) == 1 and blocks[0].type == "fence"
    assert blocks[0].content == body


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_special_directory_establishes_identity_for_ordinary_children(
    style: str,
) -> None:
    tree = build_tree(
        [
            Entry("notes  # drafts/ordinary.md"),
            Entry("notes  # drafts/another  # draft.md"),
            Entry("notes  # drafts/nested/leaf"),
        ]
    )
    settings = Settings(root="src", style=style)
    paths = special_paths(tree, settings.root)
    assert paths == frozenset(
        {
            "src/notes  # drafts",
            "src/notes  # drafts/another  # draft.md",
        }
    )
    text = render_tree(tree, settings)
    assert parse_tree(text, style, root="src", special_paths=paths) == tree
    collapsed = replace(tree, children=(replace(tree.children[0], children=()),))
    assert special_paths(collapsed, "src") == frozenset({"src/notes  # drafts"})


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
@pytest.mark.parametrize(
    "name",
    [
        "notes  # draft",
        "bad\udcff  # name",
        "back\\slash  # draft",
        "x\n  # y",
        "x  # ",
    ],
)
def test_special_name_roundtrip_preserves_bytes_and_controls(
    style: str, name: str
) -> None:
    tree = build_tree([Entry(name)])
    child = replace(tree.children[0], annotation="annotation  # stays literal ")
    tree = replace(tree, children=(child,))
    text = render_tree(tree, Settings(style=style))
    assert parse_tree(text, style, special_paths=special_paths(tree)) == tree


@pytest.mark.parametrize(
    "paths",
    [
        frozenset({"unused  # path"}),
        frozenset({"ordinary"}),
        frozenset({"other/a  # b"}),
        frozenset({"../escape  # path"}),
    ],
)
def test_special_registrations_must_match_visible_scoped_names(
    paths: frozenset[str],
) -> None:
    with pytest.raises(MarkerError):
        parse_tree("./\n└── ordinary\n", special_paths=paths)


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
@pytest.mark.parametrize("reverse", [False, True])
def test_special_name_prefixes_resolve_using_all_registered_identities(
    style: str, reverse: bool
) -> None:
    tree = build_tree([Entry("x  # y"), Entry("x  # y  # z")])
    if reverse:
        tree = replace(tree, children=tuple(reversed(tree.children)))
    printed = render_tree(tree, Settings(style=style))
    assert parse_tree(printed, style, special_paths=special_paths(tree)) == tree


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_special_parent_assignment_uses_descendant_registrations(style: str) -> None:
    tree = build_tree(
        [Entry("x  # y/a  # b"), Entry("x  # y  # z/a  # b"), Entry("ordinary")]
    )
    tree = replace(tree, children=tuple(reversed(tree.children)))
    printed = render_tree(tree, Settings(style=style))
    assert parse_tree(printed, style, special_paths=special_paths(tree)) == tree


def test_multiple_complete_special_identity_assignments_are_rejected() -> None:
    with pytest.raises(MarkerError, match="ambiguous special-path"):
        parse_tree(
            "./\n├── x  # y\n└── x  # y\n",
            special_paths=frozenset({"x  # y"}),
        )


def test_special_identity_search_limit_is_an_explicit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("treestamp.codec.MAX_IDENTITY_BRANCHES", 0)
    with pytest.raises(
        MarkerError, match="identity resolution exceeds the search limit"
    ):
        parse_tree(
            "./\n├── x  # y\n└── ordinary\n",
            special_paths=frozenset({"x  # y"}),
        )


def test_filename_and_annotation_overlap_cannot_duplicate_registered_identity() -> None:
    tree = Node(
        ".",
        "",
        "dir",
        children=(
            Node("x", "x", "file", annotation="y"),
            Node("x  # y", "x  # y", "file"),
        ),
    )
    with pytest.raises(MarkerError, match="cannot represent"):
        render_tree(tree, Settings())


@pytest.mark.parametrize("target", ["ordinary  # target", "null"])
@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_symlink_facts_cannot_be_silently_reinterpreted(
    target: str, style: str
) -> None:
    tree = build_tree([Entry("link", "symlink", target)])
    with pytest.raises(MarkerError, match="cannot represent"):
        render_tree(tree, Settings(style=style))


def test_one_space_hash_is_an_ordinary_name() -> None:
    tree = build_tree([Entry("notes # draft")])
    assert not special_paths(tree)
    assert parse_tree(render_tree(tree, Settings())) == tree


def test_initial_single_directory_chain_is_exactly_one_level() -> None:
    target = build_tree([Entry("src/package/deep/main.py")])
    initial = initial_tree(target, Settings())
    assert [node.path for node in initial.walk()] == ["src"]
    assert initial.children[0].dirs == 1
