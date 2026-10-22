"""Repository link parsing: the only path from user text to a GitHub URL."""

from __future__ import annotations

import re
from dataclasses import dataclass

_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
_REPO = re.compile(r"[A-Za-z0-9._-]{1,100}")
_LINK = re.compile(
    r"(?:(?:https?://)?(?:www\.)?github\.com/)?([^/\s]+)/([^/\s]+)(?:/(.*))?"
)
_HEX40 = re.compile(r"[0-9a-f]{40}")
_PINNED = re.compile(r"(?:tree|commit)/([0-9a-f]{40})/?")
MAX_LINK_LENGTH = 2048
MAX_REF_LENGTH = 255


class LinkError(ValueError):
    """The text is not an accepted repository link."""


@dataclass(frozen=True)
class Repository:
    owner: str
    name: str
    ref: str = "HEAD"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.name}"

    @property
    def pinned(self) -> bool:
        return _HEX40.fullmatch(self.ref) is not None

    def at(self, ref: str) -> Repository:
        return Repository(self.owner, self.name, ref)


@dataclass(frozen=True)
class ParsedLink:
    repository: Repository
    ignored: str | None = None
    """What the link carried beyond the repository, dropped with a notice."""

    @property
    def notice(self) -> str | None:
        if self.ignored is None:
            return None
        kind, _, remainder = self.ignored.partition("/")
        if kind == "blob" and "/" in remainder:
            _, _, path = remainder.partition("/")
            hint = (
                f" If {path} is the document that holds the tree, set Document to it."
                if path.lower().endswith((".md", ".markdown", ".rst", ".txt"))
                else ""
            )
            return (
                f"The link's `{self.ignored}` part was ignored; the editor reads "
                f"the default branch.{hint}"
            )
        return (
            f"The link's `{self.ignored}` part was ignored; "
            "the editor reads the default branch."
        )


def parse_link(text: str, *, allow_refs: bool = False) -> ParsedLink:
    """Reduce any GitHub link to its repository, keeping a pinned commit.

    Anything after the repository name other than a commit id is dropped and
    reported through ``ParsedLink.ignored``. With ``allow_refs``, which the
    signed-in tier will use, a ``/tree/<ref>`` segment selects that ref.
    """
    if len(text) > MAX_LINK_LENGTH:
        raise LinkError("That link is too long.")
    text = text.strip().split("#", 1)[0].split("?", 1)[0]
    match = _LINK.fullmatch(text)
    if match is None:
        raise LinkError("That does not look like a GitHub repository link.")
    owner, name, rest = match.groups()
    name = name.removesuffix(".git")
    rest = (rest or "").strip("/")
    if not rest:
        return ParsedLink(repository(owner, name))
    pinned = _PINNED.fullmatch(rest)
    if pinned is not None:
        return ParsedLink(repository(owner, name, pinned.group(1)))
    if allow_refs and rest.startswith("tree/") and len(rest) > len("tree/"):
        return ParsedLink(repository(owner, name, rest[len("tree/") :]))
    return ParsedLink(repository(owner, name), ignored=rest)


def repository(owner: str, name: str, ref: str = "HEAD") -> Repository:
    """Validate explicit components, for permalinks and the API."""
    if _OWNER.fullmatch(owner) is None:
        raise LinkError(f"{owner!r} is not a valid GitHub owner name.")
    if _REPO.fullmatch(name) is None or name in (".", ".."):
        raise LinkError(f"{name!r} is not a valid GitHub repository name.")
    _check_ref(ref)
    return Repository(owner, name, ref)


def _check_ref(ref: str) -> None:
    if not ref or len(ref) > MAX_REF_LENGTH:
        raise LinkError("A reference must be between 1 and 255 characters.")
    segments = ref.split("/")
    if (
        any(not s or s == "." or s == ".." or s.startswith("-") for s in segments)
        or any(not c.isprintable() or c.isspace() for c in ref)
        or ".." in ref
        or "@{" in ref
        or ref.endswith(".lock")
        or any(c in ref for c in "~^:?*[\\")
    ):
        raise LinkError(f"{ref!r} is not a valid reference.")
