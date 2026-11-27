"""Prepare fixed-snapshot drafts and publish them transactionally."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from treestamp.artifacts import (
    Artifact,
    ArtifactFormat,
    load_artifact,
    prepare_artifact_content,
    prepare_artifact_write,
    prepare_svg_export,
)
from treestamp.codec import render_tree
from treestamp.document import (
    ATTRIBUTION,
    Document,
    DocumentSnapshot,
    PreparedWrite,
    extract_region,
    parse_document,
    prepare_content,
    publish_write,
    render_region,
    validate_source_tree,
)
from treestamp.errors import MarkerError
from treestamp.gitio import Snapshot, capture_snapshot, document_path
from treestamp.maintenance import update
from treestamp.model import Settings, repo_path, tree_path
from treestamp.reconcile import Reconciliation
from treestamp.session import TreeSession
from treestamp.svg import render_svg
from treestamp.svg_metadata import SvgAppearance

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from treestamp.model import Node

OPEN_UPDATED_NOTICE = "Treestamp updated"
_DEFAULT_APPEARANCE = SvgAppearance()


@dataclass
class EditorState:
    session: TreeSession
    snapshot: Snapshot
    document_path: Path | None = None
    document_snapshot: DocumentSnapshot | None = None
    status: str = ""
    baseline: DocumentSnapshot | bytes | None = None
    reconciliation: Reconciliation | None = None
    source_format: ArtifactFormat = "markdown"
    svg_appearance: SvgAppearance = _DEFAULT_APPEARANCE
    artifact_warnings: tuple[str, ...] = ()

    @property
    def root(self) -> Path:
        return self.snapshot.root

    @property
    def dirty(self) -> bool:
        """Compare publishable bytes, including the loaded document's formatting."""
        document = _document(self.session)
        try:
            if isinstance(self.baseline, DocumentSnapshot):
                proposed = prepare_artifact_content(
                    Artifact(document, self.source_format, self.svg_appearance),
                    self.baseline.content,
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
    source_format: ArtifactFormat = "markdown",
    svg_appearance: SvgAppearance = _DEFAULT_APPEARANCE,
    artifact_warnings: tuple[str, ...] = (),
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
    if source_format == "svg":
        render_svg(_document(session), svg_appearance)
    baseline = saved or (_region_bytes(document) if document else accepted)
    state = EditorState(
        session,
        snapshot,
        path,
        saved,
        baseline=baseline,
        source_format=source_format,
        svg_appearance=svg_appearance,
        artifact_warnings=artifact_warnings,
    )
    if document is not None:
        state.reconciliation = Reconciliation(document.tree, session)
    state.status = _opening_status(state)
    return state


def _opening_status(state: EditorState) -> str:
    """Explain the accepted draft without mixing messages into its preparation."""
    status = "Ready to edit a new treestamp."
    if state.reconciliation is not None:
        status = OPEN_UPDATED_NOTICE if state.dirty else "Treestamp is up to date"
        remaining = state.reconciliation.remaining
        if remaining:
            noun = "annotation" if remaining == 1 else "annotations"
            status += f": {remaining} {noun} to review"
    if state.source_format == "svg":
        status += ". SVG regenerated from embedded data; writing replaces its drawing."
    if state.artifact_warnings:
        status += " " + " ".join(state.artifact_warnings)
    return status


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
        source_format: ArtifactFormat = "markdown",
        svg_appearance: SvgAppearance = _DEFAULT_APPEARANCE,
        artifact_warnings: tuple[str, ...] = (),
    ) -> None:
        document = loaded_document or (
            Document(tree, settings, hidden) if tree is not None else None
        )
        self._snapshots: dict[Path, DocumentSnapshot] = {}
        self.adopt(
            _prepare_state(
                snapshot,
                settings,
                document,
                document_path,
                document_snapshot,
                source_format,
                svg_appearance,
                artifact_warnings,
            )
        )

    def prepare_load(self, path: str) -> EditorState:
        resolved = document_path(self.state.snapshot.repo, path)
        artifact, saved = load_artifact(resolved)
        assert artifact is not None and saved is not None
        document = artifact.document
        root = self.state.snapshot.repo / document.settings.root
        snapshot = capture_snapshot(root, repository=self.state.snapshot.repo)
        return _prepare_state(
            snapshot,
            document.settings,
            document,
            saved.path,
            saved,
            artifact.format,
            artifact.appearance,
            artifact.warnings,
        )

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
        reconciliation = self.state.reconciliation
        decisions = reconciliation.snapshot() if reconciliation is not None else None
        try:
            yield
            if session.settings != settings:
                validate_source_tree(session.root, session.settings)
            _region_bytes(self.document())
            if self.state.source_format == "svg":
                self.svg_text()
        except Exception:
            session.settings = settings
            session.collapsed, session.hidden = collapsed, hidden
            session.annotations = annotations
            if reconciliation is not None and decisions is not None:
                reconciliation.restore(decisions)
            raise

    def write(self, path: str) -> str:
        repository = self.state.snapshot.repo
        destination = document_path(repository, path)
        prepared = prepare_artifact_write(
            Artifact(
                self.document(), self.state.source_format, self.state.svg_appearance
            ),
            destination,
            expected=self._snapshots.get(destination),
            repository=repository,
        )
        result = publish_write(prepared)
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
        document = self.document()
        saved = self.state.document_snapshot
        if (
            self.state.source_format == "svg"
            or saved is None
            or parse_document(saved.content, allow_absent=True) is None
        ):
            return render_region(document)
        content = prepare_content(document, document.settings.root, saved.content)
        return extract_region(content).decode("utf-8-sig", "surrogateescape")

    def svg_text(self) -> str:
        """Generate a standalone SVG without changing source identity or baseline."""
        return render_svg(self.document(), self.state.svg_appearance)

    def prepare_svg_export(
        self, path: str, *, expected: DocumentSnapshot | None = None
    ) -> PreparedWrite:
        """Prepare a copy; publication deliberately does not adopt its destination."""
        repository = self.state.snapshot.repo
        destination = document_path(repository, path)
        return prepare_svg_export(
            self.document(),
            destination,
            appearance=self.state.svg_appearance,
            source=self.state.document_path,
            expected=expected,
            repository=repository,
        )
