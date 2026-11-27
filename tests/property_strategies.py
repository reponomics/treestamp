"""Hypothesis strategies for generated tests of the codec, documents, and sessions.

Names and symlink targets are drawn the way Git supplies them: bytes decoded with
``surrogateescape``, so undecodable bytes appear as U+DC80..U+DCFF. Crafted
fragments that collide with row syntax are mixed in, because random text rarely
produces them.
"""

from __future__ import annotations

from hypothesis import strategies as st

from treestamp.model import (
    ANNOTATION_DELIMITER,
    KIND_DIR,
    KIND_GITLINK,
    KIND_SYMLINK,
)

ARROW = " -> "
GITLINK_SUFFIX = " [gitlink]"

# Row syntax, quoting, markup, and escapes that random text seldom reaches.
NAME_FRAGMENTS = (
    ANNOTATION_DELIMITER,
    " -> ",
    " ->",
    "  #",
    " # ",
    " #",
    " [gitlink]",
    " (1 file)",
    " (2 files, 3 folders)",
    "/",  # filtered from names below; kept for targets
    "\\",
    "\\x41",
    "\\u0041",
    '"',
    "'",
    "`",
    "```",
    "~~~",
    "<!-- treestamp:start -->",
    "<!-- treestamp:end -->",
    "-->",
    "├── ",
    "|-- ",
    "│   ",
    "<img src=x onerror=alert(1)>",
    " ",
    "\t",
    "\n",
    "\r",
    "\x7f",
    "\u2028",
    "\u00a0",
    "\u200b",
    "e\u0301",
    "\u00e9",
    "\u65e5\u672c",
    "\u202e",
    "\U0001f600",
    "\udcff",
    "\udc80",
)


def _from_bytes(data: bytes) -> str:
    return data.decode("utf-8", "surrogateescape")


def canonical(text: str) -> str:
    """Decode text as Git would: joined escaped bytes may form valid UTF-8."""
    return _from_bytes(text.encode("utf-8", "surrogateescape"))


_text_piece = st.one_of(
    st.sampled_from(NAME_FRAGMENTS),
    st.text(st.characters(codec="utf-8", exclude_characters="\x00/"), max_size=4),
    st.binary(min_size=1, max_size=4).map(_from_bytes),
)


def _valid_name(name: str) -> bool:
    return name not in ("", ".", "..") and "/" not in name and "\x00" not in name


names = st.one_of(
    st.text("abcdefghij0123456789._-", min_size=1, max_size=6),
    st.lists(_text_piece, min_size=1, max_size=3).map("".join).map(canonical),
).filter(_valid_name)

# Targets are blob contents, so any surrogateescape-decoded bytes are possible.
symlink_targets = st.one_of(
    st.none(),
    st.sampled_from(("null", "a  # b", "  # ", " # x", " #", "../x", "")),
    st.lists(_text_piece, min_size=1, max_size=3).map("".join).map(canonical),
    st.binary(max_size=8).map(_from_bytes),
)

# Annotations are user text: printable characters and tabs, on one line.
annotation_texts = st.one_of(
    st.just(""),
    st.lists(
        st.one_of(
            st.characters(categories=["L", "M", "N", "P", "S", "Zs"]).filter(
                str.isprintable
            ),
            st.sampled_from(("\t", "  # ", "<b>", "```", " -> ", "\\n")),
        ),
        max_size=8,
    ).map("".join),
)

repository_roots = st.one_of(
    st.just("."),
    st.lists(names, min_size=1, max_size=3).map("/".join),
)


def _shown(text: str) -> str:
    """Spacing of a printed name or target: trailing whitespace is escaped.

    Other escapes replace control characters and backslashes with backslash
    sequences, which can neither form nor break an arrow or a delimiter.
    """
    body = text.rstrip()
    return body + "\\" * (len(text) - len(body))


def is_unrepresentable_row(
    name: str, kind: str, target: str | None, annotation: str
) -> bool:
    """A test-owned reading of the printed row grammar (docs/adr/0003).

    Rows split at the first annotation delimiter, and symlinks at the first
    arrow. Registered special names are consumed before either split.
    """
    registered = (
        ANNOTATION_DELIMITER in name or ARROW in name or name.endswith(GITLINK_SUFFIX)
    )
    printed_name = "entry" if registered else _shown(name)
    suffix = {KIND_DIR: "/", KIND_GITLINK: GITLINK_SUFFIX}.get(kind, "")
    if kind == KIND_SYMLINK:
        printed_target = "null" if target is None else _shown(target)
        if target is not None and printed_target == "null":
            return True
        suffix = ARROW + printed_target
    head = printed_name + suffix
    arrow = head.find(ARROW)
    note = annotation.replace("\t", "  ")
    return (
        ANNOTATION_DELIMITER in head
        or (kind == KIND_SYMLINK and arrow != len(printed_name))
        or (kind == KIND_GITLINK and arrow != -1)
        or bool(note)
        and (head + ANNOTATION_DELIMITER).find(ANNOTATION_DELIMITER) != len(head)
    )
