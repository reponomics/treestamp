"""Generated documents: serialization, parsing, and bytes outside the managed region.

Expected facts come from the generated model, never from rendering it. The
renderer's own roundtrip check is part of the code under test, so a supported
model that fails to render is a failure, not a skipped example.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pytest
from hypothesis import assume, event, given
from hypothesis import strategies as st

from treestamp.document import (
    END_MARKER,
    START_MARKER,
    Document,
    parse_document,
    prepare_content,
    render_region,
)
from treestamp.errors import MarkerError
from treestamp.model import (
    KIND_DIR,
    KIND_FILE,
    KIND_GITLINK,
    KIND_SYMLINK,
    MAX_DEPTH,
    Node,
    Settings,
    repo_path,
)

from .property_strategies import (
    annotation_texts,
    is_unrepresentable_row,
    names,
    repository_roots,
    symlink_targets,
)

Fact = tuple[str, str, "str | None", str, "int | None", "int | None"]


@dataclass(frozen=True)
class Spec:
    """One generated row; a directory without children is printed collapsed."""

    name: str
    kind: str
    annotation: str = ""
    target: str | None = None
    children: tuple[Spec, ...] = ()
    files: int | None = None
    dirs: int | None = None
    hidden: tuple[str, ...] = ()  # names hidden beneath an expanded directory


@dataclass(frozen=True)
class Model:
    root_annotation: str
    children: tuple[Spec, ...]
    root_hidden: tuple[str, ...]
    root: str
    style: str
    show_counts: bool
    attribution: bool
    nodes: list[tuple[str, Spec]] = field(compare=False, default_factory=list)

    def __post_init__(self) -> None:
        def visit(children: tuple[Spec, ...], parent: str) -> None:
            for spec in children:
                path = f"{parent}/{spec.name}" if parent else spec.name
                self.nodes.append((path, spec))
                visit(spec.children, path)

        visit(self.children, "")

    @property
    def unrepresentable(self) -> bool:
        return any(
            is_unrepresentable_row(spec.name, spec.kind, spec.target, spec.annotation)
            for _, spec in self.nodes
        )

    def hidden(self) -> frozenset[str]:
        paths = [(name, "") for name in self.root_hidden]
        paths += [(name, path) for path, spec in self.nodes for name in spec.hidden]
        return frozenset(
            repo_path(f"{parent}/{name}" if parent else name, self.root)
            for name, parent in paths
        )

    def document(self) -> Document:
        def build(children: tuple[Spec, ...], parent: str) -> tuple[Node, ...]:
            nodes = []
            for spec in children:
                path = f"{parent}/{spec.name}" if parent else spec.name
                nodes.append(
                    Node(
                        spec.name,
                        path,
                        spec.kind,
                        build(spec.children, path),
                        spec.target,
                        spec.annotation,
                        spec.files,
                        spec.dirs,
                    )
                )
            return tuple(nodes)

        tree = Node(
            ".", "", KIND_DIR, build(self.children, ""), None, self.root_annotation
        )
        settings = Settings(self.root, self.style, self.show_counts, self.attribution)
        return Document(tree, settings, self.hidden())

    def facts(self) -> list[Fact]:
        rows: list[Fact] = [
            ("", KIND_DIR, None, _note(self.root_annotation), None, None)
        ]
        rows += [
            (path, s.kind, s.target, _note(s.annotation), s.files, s.dirs)
            for path, s in self.nodes
        ]
        return rows

    def expected_settings(self) -> Settings:
        """Style is read from connectors and count visibility from collapsed rows."""
        collapsed = any(s.kind == KIND_DIR and not s.children for _, s in self.nodes)
        return Settings(
            self.root,
            self.style if self.children else "unicode",
            self.show_counts if collapsed else True,
            self.attribution,
        )


def _note(text: str) -> str:
    """Tabs occupy two spaces; nothing else in an annotation changes."""
    return text.replace("\t", "  ")


def document_facts(document: Document) -> list[Fact]:
    return [
        (n.path, n.kind, n.target, n.annotation, n.files, n.dirs)
        for n in (document.tree, *document.tree.walk())
    ]


def _assert_matches(document: Document, model: Model) -> None:
    assert document_facts(document) == model.facts()
    assert document.settings == model.expected_settings()
    assert document.hidden == model.hidden()


_positive = st.integers(1, 99)
_counts = st.one_of(
    st.tuples(_positive, st.none()),
    st.tuples(st.none(), _positive),
    st.tuples(_positive, _positive),
)


def _hidden_names(taken: set[str]) -> st.SearchStrategy[tuple[str, ...]]:
    return st.lists(
        names.filter(lambda name: name not in taken), max_size=2, unique=True
    ).map(tuple)


@st.composite
def _spec(draw: st.DrawFn, depth: int, show_counts: bool) -> Spec:
    name = draw(names)
    kind = draw(st.sampled_from((KIND_FILE, KIND_DIR, KIND_SYMLINK, KIND_GITLINK)))
    annotation = draw(annotation_texts)
    if kind == KIND_SYMLINK:
        return Spec(name, kind, annotation, target=draw(symlink_targets))
    if kind != KIND_DIR:
        return Spec(name, kind, annotation)
    children = draw(_children(depth - 1, show_counts)) if depth else ()
    if children:
        taken = {child.name for child in children}
        return Spec(
            name, kind, annotation, children=children, hidden=draw(_hidden_names(taken))
        )
    files, dirs = draw(_counts) if show_counts else (None, None)
    return Spec(name, kind, annotation, files=files, dirs=dirs)


def _children(depth: int, show_counts: bool) -> st.SearchStrategy[tuple[Spec, ...]]:
    return st.lists(
        _spec(depth, show_counts), max_size=3, unique_by=lambda spec: spec.name
    ).map(tuple)


@st.composite
def models(draw: st.DrawFn) -> Model:
    show_counts = draw(st.booleans())
    children = draw(_children(3, show_counts))
    taken = {child.name for child in children}
    return Model(
        root_annotation=draw(annotation_texts),
        children=children,
        root_hidden=draw(_hidden_names(taken)),
        root=draw(repository_roots),
        style=draw(st.sampled_from(("unicode", "ascii"))),
        show_counts=show_counts,
        attribution=draw(st.booleans()),
    )


_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# The region finder's own boundary rule (document._BOUNDARY).
_BOUNDARY = re.compile(r"^[ \t]*<!--[ \t]*treestamp:(?:start|end)")


def _plain_markdown_line(line: str) -> bool:
    # Outside the managed region these lines would open a fence or be read as a
    # boundary marker; both are Markdown structure, not ordinary prose.
    return not _FENCE.match(line) and not _BOUNDARY.match(line.lstrip("\ufeff"))


prose_lines = (
    st.lists(
        st.one_of(
            st.characters(codec="utf-8", exclude_characters="\r\n"),
            st.sampled_from(
                ("<!-- note -->", "<!-- treestamp:config", "```", "~~~", "\udcfe")
            ),
        ),
        max_size=12,
    )
    .map("".join)
    .filter(_plain_markdown_line)
)

# A fenced example of a treestamp, which the region finder must ignore.
FENCED_EXAMPLE = ["```markdown", START_MARKER, "./", END_MARKER, "```"]


@dataclass(frozen=True)
class Framing:
    region_eol: str
    prose_eol: str
    bom: bool
    prefix: tuple[str, ...]
    suffix: tuple[str, ...]
    fenced_example: bool
    final_newline: bool

    def wrap(self, region: str) -> tuple[bytes, bytes, bytes]:
        """Return the bytes before, of, and after the region, as a file has them."""
        lines = [*self.prefix, *(FENCED_EXAMPLE if self.fenced_example else [])]
        before = ("\ufeff" if self.bom else "") + "".join(
            line + self.prose_eol for line in lines
        )
        after = "".join(self.prose_eol + line for line in self.suffix)
        body = region.replace("\n", self.region_eol)
        if not self.final_newline and not self.suffix:
            body = body.removesuffix(self.region_eol)
        elif self.suffix:
            after = after.removeprefix(self.prose_eol)
            after += self.prose_eol if self.final_newline else ""
        encode = lambda text: text.encode("utf-8", "surrogateescape")  # noqa: E731
        return encode(before), encode(body), encode(after)


framings = st.builds(
    Framing,
    region_eol=st.sampled_from(("\n", "\r\n")),
    prose_eol=st.sampled_from(("\n", "\r\n")),
    bom=st.booleans(),
    prefix=st.lists(prose_lines, max_size=3).map(tuple),
    suffix=st.lists(prose_lines, max_size=3).map(tuple),
    fenced_example=st.booleans(),
    final_newline=st.booleans(),
)


@given(models())
def test_generated_documents_render_and_parse_to_their_model(model: Model) -> None:
    document = model.document()
    event("unrepresentable" if model.unrepresentable else "representable")
    try:
        region = render_region(document)
    except MarkerError as exc:
        assert model.unrepresentable, f"unexpected rejection: {exc}"
        assert "cannot represent tree" in str(exc)
        return
    assert not model.unrepresentable, "the predicate rejects a representable row"
    _assert_matches(parse_document(region.encode("utf-8", "surrogateescape")), model)


@given(models(), models(), framings)
def test_updates_preserve_every_byte_outside_the_region(
    model: Model, replacement: Model, framing: Framing
) -> None:
    assume(not model.unrepresentable and not replacement.unrepresentable)
    before, region, after = framing.wrap(render_region(model.document()))
    content = before + region + after
    _assert_matches(parse_document(content), model)
    assert prepare_content(model.document(), model.root, content) == content

    head = before + (START_MARKER + framing.region_eol).encode()
    tail = END_MARKER.encode() + region.rpartition(END_MARKER.encode())[2] + after
    updated = prepare_content(replacement.document(), replacement.root, content)
    assert updated.startswith(head)
    assert updated.endswith(tail)
    interior = updated[len(head) : len(updated) - len(tail)]
    if framing.region_eol == "\r\n":
        assert b"\n" not in interior.replace(b"\r\n", b"")
    _assert_matches(parse_document(updated), replacement)


_unsupported_names = st.one_of(
    st.sampled_from(("", ".", "..")),
    st.tuples(names, st.sampled_from(("/", "\x00")), names).map("".join),
)
_unsupported_annotations = st.tuples(
    annotation_texts,
    st.characters(categories=["Cc", "Cf", "Zl", "Zp", "Co", "Cs"]).filter(
        lambda char: char != "\t"
    ),
).map("".join)


@given(models(), st.data())
def test_unsupported_entries_are_rejected_as_document_errors(
    model: Model, data: st.DataObject
) -> None:
    assume(not model.unrepresentable)
    document = model.document()
    taken = {child.name for child in document.tree.children}
    free = names.filter(lambda name: name not in taken)
    entry, message = data.draw(
        st.one_of(
            _unsupported_names.map(
                lambda name: (
                    Node(name, name, KIND_FILE),
                    "invalid relative path|name does not match path|duplicate tree path",
                )
            ),
            st.tuples(free, _unsupported_annotations).map(
                lambda case: (
                    Node(case[0], case[0], KIND_FILE, annotation=case[1]),
                    "annotation must be a single line",
                )
            ),
        )
    )
    tree = Node(".", "", KIND_DIR, (*document.tree.children, entry))
    with pytest.raises(MarkerError, match=message):
        render_region(Document(tree, document.settings))


@pytest.mark.parametrize(
    ("name", "kind", "target", "annotation", "representable"),
    [
        ("link", KIND_SYMLINK, "null", "", False),
        ("link", KIND_SYMLINK, None, "", True),
        ("link", KIND_SYMLINK, "a  # b", "", False),
        ("link", KIND_SYMLINK, " # x", "", False),
        ("link", KIND_SYMLINK, "  # ", "", True),  # its trailing space is escaped
        ("link", KIND_SYMLINK, "t  #", "note", False),
        ("link", KIND_SYMLINK, " #", "note", False),
        ("link", KIND_SYMLINK, "", "note", True),
        ("x ->", KIND_SYMLINK, "t", "", False),
        ("x  #", KIND_SYMLINK, "t", "", False),
        ("x -", KIND_SYMLINK, "t", "", True),
        ("x ->", KIND_GITLINK, None, "", False),
        ("x  #", KIND_GITLINK, None, "", False),
        ("a -> b", KIND_GITLINK, None, "", True),  # registered special name
        ("a  # b", KIND_SYMLINK, "t", "note", True),  # registered special name
        ("a  #", KIND_FILE, None, "note", False),
        ("a  #", KIND_FILE, None, "", True),
        ("a #", KIND_FILE, None, "note", True),
        ("x ->", KIND_FILE, None, "note", True),
    ],
)
def test_documented_representability_cases(
    name: str, kind: str, target: str | None, annotation: str, representable: bool
) -> None:
    """Each rule in docs/adr/0003, for both the predicate and the renderer."""
    assert is_unrepresentable_row(name, kind, target, annotation) is not representable
    entry = Node(name, name, kind, target=target, annotation=annotation)
    document = Document(Node(".", "", KIND_DIR, (entry,)))
    if representable:
        parsed = parse_document(render_region(document).encode())
        assert document_facts(parsed) == document_facts(document)
    else:
        with pytest.raises(MarkerError, match="cannot represent tree"):
            render_region(document)


def test_depth_beyond_the_limit_is_rejected() -> None:
    node = Node("leaf", "/".join(["d"] * MAX_DEPTH + ["leaf"]), KIND_FILE)
    for depth in range(MAX_DEPTH, 0, -1):
        path = "/".join(["d"] * depth)
        node = Node("d", path, KIND_DIR, (node,))
    with pytest.raises(MarkerError, match="depth limit"):
        render_region(Document(Node(".", "", KIND_DIR, (node,))))


_row_prefixes = st.sampled_from(
    ("", "├── ", "└── ", "│   ├── ", "|-- ", "`-- ", "    └── ")
)
_row_bodies = st.one_of(
    names,
    names.map(lambda name: name + "/"),
    st.tuples(names, symlink_targets.filter(lambda t: t is not None)).map(" -> ".join),
    st.tuples(names, annotation_texts).map("  # ".join),
    st.sampled_from(("dir/ (1 file)", "dir/ (0 files)", "x [gitlink]", "./", ".")),
)
_interior_lines = st.one_of(
    st.tuples(_row_prefixes, _row_bodies).map("".join),
    st.sampled_from(
        (
            "",
            "```sh",
            "```",
            "~~~",
            "<!-- treestamp:config",
            "-->",
            'root = "a"',
            'hidden = ["a/b"]',
            'special_paths = [{row = 1, path = "a  # b"}]',
            'special_paths = [{row = 0, path = {git_bytes = "ff"}}]',
            "Maintained with [treestamp](https://github.com/reponomics/treestamp)",
        )
    ),
    prose_lines,
)


@given(
    st.one_of(
        st.lists(_interior_lines, max_size=12).map(
            lambda lines: "\n".join([START_MARKER, *lines, END_MARKER, ""]).encode(
                "utf-8", "surrogateescape"
            )
        ),
        st.binary(max_size=200),
    )
)
def test_parsed_documents_rerender_to_the_same_meaning(content: bytes) -> None:
    try:
        document = parse_document(content)
    except MarkerError:
        return
    rendered = render_region(document).encode("utf-8", "surrogateescape")
    again = parse_document(rendered)
    assert document_facts(again) == document_facts(document)
    assert (again.settings, again.hidden) == (document.settings, document.hidden)
