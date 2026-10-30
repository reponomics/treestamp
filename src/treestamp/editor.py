"""Prepare fixed-snapshot drafts and publish them transactionally."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from treestamp.codec import render_tree
from treestamp.document import (
    ATTRIBUTION,
    Document,
    DocumentSnapshot,
    load_document,
    prepare_content,
    render_region,
    validate_source_tree,
    write_document,
)
from treestamp.errors import MarkerError
from treestamp.gitio import Snapshot, capture_snapshot, document_path
from treestamp.maintenance import update
from treestamp.model import Settings, repo_path, tree_path
from treestamp.session import TreeSession

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from treestamp.model import Node

OPEN_UPDATED_NOTICE = "Treestamp updated"


@dataclass
class EditorState:
    session: TreeSession
    snapshot: Snapshot
    document_path: Path | None = None
    document_snapshot: DocumentSnapshot | None = None
    status: str = ""
    baseline: DocumentSnapshot | bytes | None = None

    @property
    def root(self) -> Path:
        return self.snapshot.root

    @property
    def dirty(self) -> bool:
        """Compare publishable bytes, including the loaded document's formatting."""
        document = _document(self.session)
        try:
            if isinstance(self.baseline, DocumentSnapshot):
                proposed = prepare_content(
                    document, document.settings.root, self.baseline.content
                )
                return proposed != self.baseline.content
            return _region_bytes(document) != self.baseline
        except MarkerError:
            # Defensive guard for direct session mutation outside edit().
            return True


def _document(session: TreeSession) -> Document:
    hidden = frozenset(
        repo_path(path, session.settings.root) for path in session.saved_hidden()
    )
    return Document(session.printed_tree(), session.settings, hidden)


def _region_bytes(document: Document) -> bytes:
    return render_region(document).encode("utf-8", "surrogateescape")


def _prepare_state(
    snapshot: Snapshot,
    settings: Settings,
    document: Document | None,
    path: Path | None,
    saved: DocumentSnapshot | None,
) -> EditorState:
    validate_source_tree(snapshot.tree, settings)
    hidden = (
        frozenset(tree_path(item, settings.root) for item in document.hidden)
        if document
        else frozenset()
    )
    tree = (
        update(document.tree, snapshot.tree, settings, hidden=hidden)
        if document
        else None
    )
    session = TreeSession(snapshot.tree, settings, tree, hidden)
    accepted = _region_bytes(_document(session))
    baseline = saved or (_region_bytes(document) if document else accepted)
    state = EditorState(session, snapshot, path, saved, baseline=baseline)
    state.status = "Ready to edit a new treestamp."
    if document is not None:
        state.status = OPEN_UPDATED_NOTICE if state.dirty else "Treestamp is up to date"
    return state


class EditorController:
    """Loads are prepared before adoption; failed writes never alter the draft."""

    def __init__(
        self,
        snapshot: Snapshot,
        settings: Settings,
        tree: Node | None = None,
        hidden: frozenset[str] = frozenset(),
        document_path: Path | None = None,
        document_snapshot: DocumentSnapshot | None = None,
        loaded_document: Document | None = None,
    ) -> None:
        document = loaded_document or (
            Document(tree, settings, hidden) if tree is not None else None
        )
        self._snapshots: dict[Path, DocumentSnapshot] = {}
        self.adopt(
            _prepare_state(
                snapshot, settings, document, document_path, document_snapshot
            )
        )

    def prepare_load(self, path: str) -> EditorState:
        resolved = document_path(self.state.snapshot.repo, path)
        document, saved = load_document(resolved)
        assert document is not None and saved is not None
        root = self.state.snapshot.repo / document.settings.root
        snapshot = capture_snapshot(root, repository=self.state.snapshot.repo)
        return _prepare_state(snapshot, document.settings, document, saved.path, saved)

    def prepare_new(self, root: str) -> EditorState:
        # Accept ordinary dialog spellings while retaining canonical Git paths.
        # PurePosixPath leaves '..' intact so validation still rejects traversal.
        settings = Settings(root=PurePosixPath(root).as_posix() if root else root)
        # Validate before joining; an absolute or escaping path cannot select
        # another repository through a root-selection control.
        repo_path("", settings.root)
        snapshot = capture_snapshot(
            self.state.snapshot.repo / settings.root,
            repository=self.state.snapshot.repo,
        )
        return _prepare_state(snapshot, settings, None, None, None)

    def adopt(self, candidate: EditorState) -> None:
        self.state = candidate
        saved = candidate.document_snapshot
        self._snapshots = {saved.path: saved} if saved is not None else {}

    @property
    def dirty(self) -> bool:
        return self.state.dirty

    def document(self) -> Document:
        return _document(self.state.session)

    @contextmanager
    def edit(self) -> Iterator[None]:
        """Keep the accepted session intact when a candidate edit cannot export."""
        session = self.state.session
        settings = session.settings
        collapsed, hidden = session.collapsed.copy(), session.hidden.copy()
        annotations = session.annotations.copy()
        try:
            yield
            if session.settings != settings:
                validate_source_tree(session.root, session.settings)
            _region_bytes(self.document())
        except Exception:
            session.settings = settings
            session.collapsed, session.hidden = collapsed, hidden
            session.annotations = annotations
            raise

    def create(self, path: str) -> str:
        return self._write(path, create=True)

    def write(self, path: str) -> str:
        return self._write(path, create=False)

    def _write(self, path: str, *, create: bool) -> str:
        repository = self.state.snapshot.repo
        destination = document_path(repository, path)
        result = write_document(
            self.document(),
            destination,
            create=create,
            expected=None if create else self._snapshots.get(destination),
            repository=repository,
        )
        self._snapshots[result.path] = result
        self.state.document_path = result.path
        self.state.document_snapshot = result
        self.state.baseline = result
        return f"Wrote treestamped document: {result.path}"

    def preview(self) -> str:
        session = self.state.session
        tree = render_tree(session.printed_tree(), session.settings)
        return tree + (f"\n{ATTRIBUTION}\n" if session.settings.attribution else "")

    def region_text(self) -> str:
        """Print the complete treestamp without modifying the draft or document."""
        return render_region(self.document())
