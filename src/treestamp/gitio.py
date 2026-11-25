"""Git index snapshot adapters; no editor or document dependencies."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from treestamp import sources
from treestamp.errors import ExecutionError, GitEnvironmentError, MarkerError
from treestamp.model import KIND_DIR, KIND_SYMLINK, Entry, Node, build_tree

MAX_OUTPUT_BYTES = 64 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class Snapshot:
    """A fixed repository tree, projected beneath an absolute lexical root."""

    repo: Path
    root: Path
    tree: Node


def checked_path(path: Path) -> Path:
    """Normalize lexically, then reject symlinks in every existing component."""
    normalized = Path(os.path.abspath(path))
    for component in (*reversed(normalized.parents), normalized):
        try:
            mode = component.lstat().st_mode
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise ExecutionError(f"cannot inspect {component}: {exc}") from exc
        if stat.S_ISLNK(mode):
            raise MarkerError(f"refusing to follow symbolic link: {component}")
    return normalized


def _document_relative_path(value: str | Path) -> Path:
    text = os.fspath(value)
    native, windows = Path(text), PureWindowsPath(text)
    if (
        not text
        or native.is_absolute()
        or windows.drive
        or windows.root
        or text.startswith("~")
        or ".." in native.parts
        or ".." in windows.parts
        or "\x00" in text
    ):
        raise MarkerError(
            "document path must be relative to the repository root "
            "without parent traversal"
        )
    if native == Path("."):
        raise MarkerError("document path must name a file")
    return native


def _check_document_repository(repo: Path, destination: Path) -> None:
    relative = destination.relative_to(repo)
    for parent in relative.parents:
        if parent != Path(".") and (repo / parent / ".git").exists():
            raise MarkerError("document path crosses into another repository")
    # Uninitialized submodules have no .git marker, but remain repository boundaries.
    rows = _git(repo, "ls-files", "--stage", "-z").split(b"\0")
    path = relative.as_posix()
    for row in rows:
        metadata, separator, raw_path = row.partition(b"\t")
        if separator and metadata.startswith(b"160000 "):
            submodule = _decode(raw_path)
            if path == submodule or path.startswith(submodule + "/"):
                raise MarkerError("document path crosses into a submodule")


def document_path(repository: Path, value: str | Path) -> Path:
    """Resolve a document inside the selected repository, without changing it."""
    relative = _document_relative_path(value)
    repo = checked_path(repository)
    destination = checked_path(repo / relative)
    if not destination.is_relative_to(repo):
        raise MarkerError("document path is outside the selected repository")
    _check_document_repository(repo, destination)
    return destination


def _decode(raw: bytes) -> str:
    return raw.decode("utf-8", "surrogateescape")


def _git(repo: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    executable = shutil.which("git")
    if executable is None:
        raise GitEnvironmentError("git is not on PATH")
    argv = [executable, "-c", "core.quotePath=false", *args]
    try:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            result = subprocess.run(  # noqa: S603
                argv,
                cwd=repo,
                stdout=output,
                stderr=errors,
                check=False,
                input=input_bytes,
                timeout=GIT_TIMEOUT_SECONDS,
            )
            output.seek(0)
            raw = output.read(MAX_OUTPUT_BYTES + 1)
            errors.seek(0)
            stderr = _decode(errors.read(8192)).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitEnvironmentError(f"cannot run git {args[0]}: {exc}") from exc
    if result.returncode:
        raise GitEnvironmentError(f"git {args[0]} failed: {stderr}")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise GitEnvironmentError("Git output exceeds the collection byte limit")
    return raw


def repo_root(start: Path) -> Path:
    """Find the worktree containing root, including roots absent on disk."""
    existing = checked_path(start)
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    if not existing.is_dir():
        existing = existing.parent
    raw = _git(existing, "rev-parse", "--show-toplevel")
    return checked_path(Path(_decode(raw).removesuffix("\n")))


def _prefix(repo: Path, root: Path) -> str:
    try:
        relative = root.relative_to(repo)
    except ValueError as exc:
        raise GitEnvironmentError(f"root is outside repository: {root}") from exc
    return "" if relative == Path(".") else relative.as_posix() + "/"


def _tree_record(row: bytes) -> tuple[str, str, str]:
    meta, separator, path_raw = row.partition(b"\t")
    fields = meta.split()
    mode = fields[0].decode("ascii", "replace") if fields else ""
    kind = sources.MODE_KINDS.get(mode)
    if not separator or len(fields) != 3 or kind is None or kind == KIND_DIR:
        raise GitEnvironmentError("invalid Git tree record")
    return _decode(path_raw), kind, fields[2].decode("ascii")


def _entries(repo: Path, tree_id: str, prefix: str) -> dict[str, Entry]:
    raw = _git(repo, "ls-tree", "-r", "-z", "--full-tree", tree_id)
    rows = [row for row in raw.split(b"\0") if row]
    if len(rows) > sources.MAX_ENTRIES:
        raise GitEnvironmentError("Git tree exceeds the collection entry limit")
    entries: dict[str, Entry] = {}
    links: dict[str, str] = {}
    for row in rows:
        path, kind, object_id = _tree_record(row)
        if prefix and path == prefix[:-1]:
            raise MarkerError(f"selected root is a tracked leaf: {path!r}")
        if not path.startswith(prefix):
            continue
        path = path[len(prefix) :]
        entries[path] = Entry(path, kind)
        if kind == KIND_SYMLINK:
            links[path] = object_id
    for path, target in _symlink_targets(repo, links).items():
        entries[path] = Entry(path, KIND_SYMLINK, target=target)
    return entries


def _symlink_targets(repo: Path, links: dict[str, str]) -> dict[str, str]:
    if not links:
        return {}
    raw = _git(
        repo,
        "cat-file",
        "--batch",
        input_bytes=("\n".join(links.values()) + "\n").encode("ascii"),
    )
    targets: dict[str, str] = {}
    offset = 0
    for path in links:
        header_end = raw.find(b"\n", offset)
        header = raw[offset:header_end].split()
        if header_end < 0 or len(header) != 3 or header[1] != b"blob":
            raise GitEnvironmentError(f"cannot read symlink blob: {path}")
        try:
            size = int(header[2])
        except ValueError as exc:
            raise GitEnvironmentError(f"invalid symlink blob size: {path}") from exc
        start = header_end + 1
        end = start + size
        if size < 0 or end >= len(raw) or raw[end : end + 1] != b"\n":
            raise GitEnvironmentError(f"incomplete symlink blob: {path}")
        targets[path] = _decode(raw[start:end])
        offset = end + 1
    return targets


def capture_snapshot(root: Path, *, repository: Path | None = None) -> Snapshot:
    """Capture the staged index, retaining the selected repository when provided."""
    root = checked_path(root)
    repo = repo_root(root) if repository is None else checked_path(repository)
    prefix = _prefix(repo, root)
    tree_id = _git(repo, "write-tree").decode("ascii").strip()
    entries = _entries(repo, tree_id, prefix)
    tree = build_tree(entries.values())
    return Snapshot(repo, root, tree)
