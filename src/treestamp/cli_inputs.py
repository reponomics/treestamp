"""Resolve command inputs from cwd while retaining repository-owned identities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

from treestamp.document import (
    DEFAULT_DOCUMENT_FILE,
    Document,
    DocumentSnapshot,
    extract_region,
    load_document,
)
from treestamp.errors import MarkerError
from treestamp.gitio import capture_snapshot, checked_path, document_path, repo_root
from treestamp.model import Settings

if TYPE_CHECKING:
    from treestamp.editor import EditorController


def native_path(value: str) -> Path:
    """Reject symlink traversal before normalization can erase link/.. pairs."""
    path = Path(value)
    windows = PureWindowsPath(value)
    if (
        not value
        or "\x00" in value
        or ((windows.drive or windows.root) and not path.is_absolute())
    ):
        raise MarkerError("path must be a nonempty native filesystem path")
    absolute = path.absolute()
    for parent in reversed(absolute.parents):
        checked_path(parent)
    return checked_path(absolute)


def document_input(value: str | None) -> tuple[Path, Path]:
    """Explicit and implicit document paths both follow the caller's cwd."""
    destination = native_path(DEFAULT_DOCUMENT_FILE if value is None else value)
    if destination.is_dir():
        raise MarkerError("document path must name a file")
    repository = repo_root(destination)
    return repository, document_path(repository, destination.relative_to(repository))


@dataclass(frozen=True)
class LoadedSource:
    repository: Path
    path: Path
    document: Document | None
    saved: DocumentSnapshot | None

    def region_text(self) -> str:
        """Extract stored bytes without consulting a new source snapshot."""
        assert self.document is not None and self.saved is not None
        return extract_region(self.saved.content).decode("utf-8-sig", "surrogateescape")

    def editor(self) -> EditorController:
        from treestamp.editor import EditorController

        assert self.document is not None and self.saved is not None
        settings = self.document.settings
        snapshot = capture_snapshot(
            self.repository / settings.root, repository=self.repository
        )
        return EditorController(
            snapshot,
            settings,
            document_path=self.path,
            document_snapshot=self.saved,
            loaded_document=self.document,
        )


def read_source(value: str | None, *, allow_absent: bool = False) -> LoadedSource:
    repository, path = document_input(value)
    document, saved = load_document(path, allow_absent=allow_absent)
    return LoadedSource(repository, path, document, saved)


def new_editor(value: str | None) -> EditorController:
    from treestamp.editor import EditorController

    selected = native_path("." if value is None else value)
    if selected.is_file():
        selected = selected.parent
    if not selected.is_dir():
        raise MarkerError("new requires an existing directory or regular file")
    repository = repo_root(selected)
    settings = Settings(root=selected.relative_to(repository).as_posix())
    snapshot = capture_snapshot(selected, repository=repository)
    return EditorController(snapshot, settings)
