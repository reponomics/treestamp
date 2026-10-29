"""Open and edit a document against one immutable repository snapshot."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import posixpath
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from treestamp.codec import format_counts, render_tree
from treestamp.document import (
    Document,
    extract_region,
    parse_document,
    prepare_content,
    render_region,
    validate_source_tree,
)
from treestamp.errors import MarkerError
from treestamp.maintenance import update
from treestamp.model import (
    KIND_SYMLINK,
    Settings,
    path_value,
    read_path_value,
    repo_path,
    tree_path,
    validate_path,
)
from treestamp.session import SessionState, TreeSession
from treestamp.sources import tree_from_records
from treestamp_web.cache import Snapshot, SnapshotCache
from treestamp_web.examples import bundled_default_branch, bundled_tree
from treestamp_web.github import BODY_CAP, TooLargeError
from treestamp_web.links import LinkError, Repository, parse_link, repository

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from treestamp.model import Node
    from treestamp_web.config import Config
    from treestamp_web.github import GitHubClient, Resolved

DEFAULT_DOCUMENT = "README.md"
DOCUMENT_CAP = 1024 * 1024
OPEN_NOTICE = "Treestamp updated"
OPERATIONS = (
    "restore",
    "present",
    "toggle",
    "expand",
    "collapse",
    "hide",
    "unhide",
    "unhide_all",
    "annotate",
)
PARAMETERS = ("url", "owner", "repo", "ref", "root", "document")


class PreviewError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        *,
        retry_after: int | None = None,
        extra: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.status, self.code, self.retry_after = status, code, retry_after
        self.extra = dict(extra or {})


def _path_text(value: object, what: str) -> str:
    try:
        return read_path_value(value)
    except MarkerError as exc:
        raise PreviewError(400, "invalid_state", f"{what}: {exc}") from None


def _display(value: str) -> str:
    return value.encode("utf-8", "surrogateescape").decode("utf-8", "backslashreplace")


def _root(raw: str | None) -> str:
    # Normalize dialog spelling without resolving '..' before validation.
    root = PurePosixPath(raw or ".").as_posix()
    try:
        Settings(root=root)
    except MarkerError as exc:
        raise PreviewError(400, "invalid_settings", f"invalid root: {exc}") from None
    return root


def _document(raw: str | None) -> str:
    if raw == "":
        return ""
    document = DEFAULT_DOCUMENT if raw is None else raw
    try:
        validate_path(document)
    except MarkerError as exc:
        raise PreviewError(
            400, "invalid_settings", f"invalid document: {exc}"
        ) from None
    if posixpath.normpath(document) != document:
        raise PreviewError(
            400, "invalid_settings", "document must be a normalized path"
        )
    return document


@dataclass(frozen=True)
class PreviewRequest:
    repository: Repository
    root: str = "."
    document: str = DEFAULT_DOCUMENT
    explicit_document: bool = False
    notice: str | None = None


def parse_request(params: Mapping[str, str | None]) -> PreviewRequest:
    unknown = params.keys() - set(PARAMETERS)
    if unknown:
        raise PreviewError(
            400, "invalid_settings", f"unknown parameters: {', '.join(sorted(unknown))}"
        )
    url, owner, name, ref = (params.get(k) for k in ("url", "owner", "repo", "ref"))
    notice = None
    try:
        if url:
            parsed = parse_link(url)
            repo, notice = parsed.repository, parsed.notice
        elif owner and name:
            repo = repository(owner, name, ref or "HEAD")
        else:
            raise LinkError("Provide a repository link, or an owner and repo.")
    except LinkError as exc:
        raise PreviewError(400, "invalid_link", str(exc)) from None
    if repo.ref != "HEAD" and not repo.pinned:
        raise PreviewError(
            400,
            "invalid_link",
            "branches and tags are not supported; the editor reads the default branch",
        )
    return PreviewRequest(
        repo,
        _root(params.get("root")),
        _document(params.get("document")),
        bool(params.get("document")),
        notice,
    )


def parse_preview_body(data: object) -> PreviewRequest:
    """Decode explicit source identities before applying ordinary Open validation."""
    if not isinstance(data, dict):
        raise PreviewError(400, "invalid_settings", "request body must be an object")
    params: dict[str, str | None] = {}
    for name, value in data.items():
        if name in ("root", "document"):
            params[name] = _path_text(value, name)
        elif isinstance(value, str):
            params[name] = value
        else:
            raise PreviewError(400, "invalid_settings", f"{name} must be a string")
    return parse_request(params)


@dataclass(frozen=True)
class Operation:
    type: str
    path: str = ""
    text: str = ""

    @classmethod
    def from_dict(cls, data: object) -> Operation:
        if not isinstance(data, dict) or data.get("type") not in OPERATIONS:
            raise PreviewError(
                400, "invalid_op", f"op.type must be one of {', '.join(OPERATIONS)}"
            )
        if data.keys() - {"type", "path", "text"}:
            raise PreviewError(400, "invalid_op", "unknown operation fields")
        path = _path_text(data.get("path", ""), "op.path")
        text = data.get("text", "")
        if not isinstance(text, str):
            raise PreviewError(400, "invalid_op", "op.text must be a string")
        return cls(str(data["type"]), path, text)

    def apply(self, session: TreeSession) -> None:
        actions = {
            "toggle": session.toggle,
            "expand": session.expand,
            "collapse": session.collapse,
            "hide": session.hide,
            "unhide": session.unhide,
        }
        try:
            if self.type in actions:
                actions[self.type](self.path)
            elif self.type == "unhide_all":
                session.unhide_all()
            elif self.type == "annotate":
                session.set_annotation(self.path, self.text)
        except MarkerError as exc:
            raise PreviewError(400, "invalid_op", str(exc)) from None


def _baseline(value: object) -> bytes | None:
    if value is None:
        return None
    try:
        if not isinstance(value, str):
            raise ValueError
        decoded = base64.b64decode(value, validate=True)
        parse_document(decoded)
        return decoded
    except (ValueError, binascii.Error, MarkerError):
        raise PreviewError(400, "invalid_state", "invalid document baseline") from None


@dataclass(frozen=True)
class Envelope:
    curation: SessionState
    source: Mapping[str, object]
    baseline: bytes | None
    generation: str
    revision: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "curation": self.curation.to_dict(),
            "source": dict(self.source),
            "baseline": None
            if self.baseline is None
            else base64.b64encode(self.baseline).decode("ascii"),
            "generation": self.generation,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, data: object) -> Envelope:
        if (
            not isinstance(data, dict)
            or set(data)
            != {"version", "curation", "source", "baseline", "generation", "revision"}
            or data["version"] != 1
        ):
            raise PreviewError(400, "invalid_state", "invalid session envelope")
        generation, revision, baseline = (
            data["generation"],
            data["revision"],
            data["baseline"],
        )
        if (
            not isinstance(generation, str)
            or not generation
            or type(revision) is not int
            or revision < 0
        ):
            raise PreviewError(
                400, "invalid_state", "invalid session generation or revision"
            )
        decoded = _baseline(baseline)
        source = data["source"]
        if not isinstance(source, dict):
            raise PreviewError(400, "invalid_state", "invalid session source")
        try:
            state = SessionState.from_dict(data["curation"])
        except MarkerError as exc:
            raise PreviewError(400, "invalid_state", str(exc)) from None
        return cls(state, source, decoded, generation, revision)


@dataclass(frozen=True)
class OpRequest:
    repository: Repository
    root: str
    envelope: Envelope
    op: Operation
    reveal: bool = False
    document: str = DEFAULT_DOCUMENT


def _source(
    repo: Repository, commit: str, root: str, document: str
) -> dict[str, object]:
    return {
        "owner": repo.owner,
        "repo": repo.name,
        "commit": commit,
        "root": path_value(root),
        "document": path_value(document),
    }


def _operation_repository(data: Mapping[str, object]) -> Repository:
    owner, name, ref = (data.get(k) for k in ("owner", "repo", "ref"))
    if not all(isinstance(v, str) and v for v in (owner, name, ref)):
        raise PreviewError(400, "invalid_link", "owner, repo, and ref are required")
    try:
        repo = repository(str(owner), str(name), str(ref))
    except LinkError as exc:
        raise PreviewError(400, "invalid_link", str(exc)) from None
    if not repo.pinned:
        raise PreviewError(400, "invalid_link", "ref must be a 40-character commit id")
    return repo


def parse_op_request(data: object) -> OpRequest:
    if not isinstance(data, dict):
        raise PreviewError(400, "invalid_op", "request body must be an object")
    if data.keys() - {
        "owner",
        "repo",
        "ref",
        "root",
        "document",
        "state",
        "op",
        "reveal",
    }:
        raise PreviewError(400, "invalid_op", "unknown request fields")
    repo = _operation_repository(data)
    root = _root(_path_text(data.get("root", "."), "root"))
    document = _document(_path_text(data.get("document", DEFAULT_DOCUMENT), "document"))
    op = Operation.from_dict(data.get("op"))
    envelope = Envelope.from_dict(data.get("state"))
    if (
        envelope.source != _source(repo, repo.ref, root, document)
        or envelope.curation.settings.root != root
    ):
        raise PreviewError(
            400, "invalid_state", "session source does not match the request"
        )
    reveal = data.get("reveal", False)
    if not isinstance(reveal, bool):
        raise PreviewError(400, "invalid_op", "reveal must be a boolean")
    return OpRequest(repo, root, envelope, op, reveal, document)


def _row(session: TreeSession, node: Node, depth: int) -> dict[str, object]:
    row: dict[str, object] = {
        "path": path_value(node.path),
        "key": node.path.encode("utf-8", "surrogateescape").hex(),
        "name": _display(node.name) if node.path else ".",
        "kind": node.kind,
        "depth": depth,
        "annotation": session.annotations.get(node.path, ""),
        "hidden": bool(node.path) and session.is_hidden(node.path),
    }
    if node.is_dir:
        files, dirs = session.immediate_counts(node.path)
        row["collapsed"] = bool(node.path) and session.is_visibly_collapsed(node.path)
        row["files"], row["dirs"] = files, dirs
        row["counts"] = format_counts(
            files if session.show_counts else None,
            dirs if session.show_counts else None,
        )
    if node.kind == KIND_SYMLINK and node.target is not None:
        row["target"] = _display(node.target)
    return row


def _rows(session: TreeSession, reveal: bool) -> list[dict[str, object]]:
    session.show_hidden = reveal
    try:
        return [_row(session, node, depth) for node, depth in session.visible_rows()]
    finally:
        session.show_hidden = False


@dataclass(frozen=True)
class Preview:
    repository: Repository
    commit: str
    tree_id: str
    root: str
    settings: Settings
    entries: int
    root_children: int
    tree: str
    region: str
    warnings: list[str]
    state: dict[str, object]
    rows: list[dict[str, object]]
    document: str
    loaded: bool
    dirty: bool
    notice: str | None = None
    default_branch: str | None = None

    def permalink(self, public_base_url: str | None) -> str:
        root, document = path_value(self.root), path_value(self.document)
        query = {"root": root} if isinstance(root, str) else {}
        if isinstance(document, str) and document != DEFAULT_DOCUMENT:
            query["document"] = document
        path = (
            f"/{self.repository.owner}/{self.repository.name}@{self.commit}"
            f"?{urlencode(query)}"
        )
        if not isinstance(root, str) or not isinstance(document, str):
            encoded = json.dumps(self.state, ensure_ascii=True).encode("ascii")
            fragment = base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
            path += "#s=" + fragment
        return f"{public_base_url.rstrip('/')}{path}" if public_base_url else path

    def to_dict(self, public_base_url: str | None) -> dict[str, object]:
        settings: dict[str, object] = asdict(self.settings)
        settings["root"] = path_value(self.settings.root)
        return {
            "repository": {
                "owner": self.repository.owner,
                "name": self.repository.name,
                "url": self.repository.url,
                "default_branch": self.default_branch,
            },
            "ref": {
                "requested": self.repository.ref,
                "commit": self.commit,
                "tree": self.tree_id,
            },
            "root": path_value(self.root),
            "document": path_value(self.document),
            "loaded": self.loaded,
            "dirty": self.dirty,
            "notice": self.notice,
            "settings": settings,
            "entries": self.entries,
            "root_children": self.root_children,
            "tree": self.tree,
            "region": self.region,
            "warnings": list(self.warnings),
            "permalink": self.permalink(public_base_url),
            "state": self.state,
            "rows": self.rows,
        }


@dataclass
class _Target:
    resolved: Resolved
    root: str
    node: Node
    default_branch: str | None = None


class PreviewService:
    def __init__(
        self,
        client: GitHubClient,
        config: Config,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._client, self._config = client, config
        self._snapshots = SnapshotCache(config, clock)

    def stats(self) -> dict[str, int]:
        return self._snapshots.stats()

    def close(self) -> None:
        self._snapshots.close()

    async def preview(self, request: PreviewRequest) -> Preview:
        repo = request.repository
        snapshot, acquired = await self._preview_snapshot(repo)
        loaded = await self._load_document(snapshot, request, acquired)
        root = request.root if loaded is None else loaded[0].settings.root
        target = await self._target(repo, snapshot, root, acquired)
        settings = Settings(root=root) if loaded is None else loaded[0].settings
        self._preflight(target.node, settings)
        if loaded is None:
            session = TreeSession(target.node, Settings(root=root))
            baseline = None
        else:
            document, baseline = loaded
            hidden = frozenset(tree_path(path, root) for path in document.hidden)
            curated = update(
                document.tree, target.node, document.settings, hidden=hidden
            )
            session = TreeSession(target.node, document.settings, curated, hidden)
        envelope = Envelope(
            session.state(),
            _source(repo, snapshot.resolved.commit, root, request.document),
            baseline,
            str(uuid.uuid4()),
        )
        result = self._compose(
            repo,
            target,
            session,
            request.document,
            envelope,
            opening=True,
            warnings=[request.notice] if request.notice else [],
        )
        if acquired:
            self._snapshots.put(repo, snapshot)
        return result

    async def apply(self, request: OpRequest) -> Preview:
        snapshot = self._cached_snapshot(request.repository)
        if snapshot is None:
            raise _snapshot_unavailable()
        target = await self._target(request.repository, snapshot, request.root, False)
        self._preflight(target.node, request.envelope.curation.settings)
        try:
            session = TreeSession.restore(target.node, request.envelope.curation)
        except MarkerError as exc:
            raise PreviewError(400, "invalid_state", str(exc)) from None
        request.op.apply(session)
        envelope = Envelope(
            session.state(),
            request.envelope.source,
            request.envelope.baseline,
            request.envelope.generation,
            request.envelope.revision + int(request.op.type != "restore"),
        )
        return self._compose(
            request.repository,
            target,
            session,
            request.document,
            envelope,
            reveal=request.reveal,
        )

    async def _load_document(
        self, snapshot: Snapshot, request: PreviewRequest, acquired: bool
    ) -> tuple[Document, bytes] | None:
        if not request.document:
            return None
        record = next(
            (row for row in snapshot.records if row.path == request.document), None
        )
        if record is None:
            if request.explicit_document:
                raise PreviewError(
                    404,
                    "not_found",
                    f"{request.document} does not exist in this snapshot",
                )
            return None
        if record.mode not in ("100644", "100755"):
            raise PreviewError(
                422,
                "curation",
                f"{request.document} is not a regular file in this snapshot",
            )
        try:
            content = await self._blob(
                request.repository, snapshot, record.object_id, acquired, DOCUMENT_CAP
            )
        except TooLargeError:
            raise PreviewError(
                422, "curation", f"{request.document} is larger than the service reads"
            ) from None
        try:
            parsed = parse_document(
                content,
                location=request.document,
                allow_absent=not request.explicit_document,
            )
            if parsed is None:
                return None
            return parsed, extract_region(content, location=request.document)
        except MarkerError as exc:
            raise PreviewError(422, "curation", str(exc)) from None

    async def _blob(
        self,
        repo: Repository,
        snapshot: Snapshot,
        object_id: str,
        acquired: bool,
        cap: int = BODY_CAP,
    ) -> bytes:
        content = snapshot.blobs.get(object_id)
        if content is None:
            if not acquired:
                raise _snapshot_unavailable()
            content = await self._client.blob(repo.owner, repo.name, object_id, cap=cap)
            snapshot.blobs[object_id] = content
        if len(content) > cap:
            raise TooLargeError("a GitHub response exceeds the size limit")
        return content

    def _cached_snapshot(self, repo: Repository) -> Snapshot | None:
        # These are shipped offline fixtures, not evidence authorizing any
        # GitHub acquisition. Missing fixture objects never fall through to it.
        if bundled := bundled_tree(repo):
            resolved, records = bundled
            return Snapshot(0, resolved, records, bundled_default_branch(repo), {})
        return self._snapshots.get(repo)

    async def _preview_snapshot(self, repo: Repository) -> tuple[Snapshot, bool]:
        if repo.pinned and (cached := self._cached_snapshot(repo)) is not None:
            return cached, False
        metadata = await self._client.public_repository(repo.owner, repo.name)
        self._snapshots.discard_other_identities(repo, metadata.identity)
        resolved = await self._client.resolve(
            repo.owner, repo.name, metadata.default_branch
        )
        if repo.pinned and repo.ref != resolved.commit:
            raise _snapshot_unavailable()
        previous = self._snapshots.get(repo.at(resolved.commit))
        records = (
            previous.records
            if previous is not None
            else await self._client.tree(repo.owner, repo.name, resolved.tree)
        )
        snapshot = Snapshot(
            metadata.identity,
            resolved,
            records,
            metadata.default_branch,
            dict(previous.blobs) if previous is not None else {},
        )
        return snapshot, True

    @staticmethod
    def _preflight(node: Node, settings: Settings) -> None:
        try:
            validate_source_tree(node, settings)
        except MarkerError as exc:
            raise PreviewError(422, "curation", str(exc)) from None

    async def _target(
        self, repo: Repository, snapshot: Snapshot, root: str, acquired: bool
    ) -> _Target:
        records = snapshot.records
        if root != "." and any(
            row.path == root and row.type != "tree" for row in records
        ):
            raise PreviewError(
                422,
                "curation",
                f"selected root {root!r} is not a directory in this snapshot",
            )
        prefix = "" if root == "." else root + "/"
        targets = await self._symlink_targets(repo, snapshot, prefix, acquired)
        try:
            node = tree_from_records(records, prefix=prefix, symlink_targets=targets)
        except MarkerError as exc:
            raise PreviewError(422, "curation", str(exc)) from None
        return _Target(snapshot.resolved, root, node, snapshot.default_branch)

    def _compose(
        self,
        repo: Repository,
        target: _Target,
        session: TreeSession,
        document: str,
        envelope: Envelope,
        *,
        reveal: bool = False,
        opening: bool = False,
        warnings: list[str] | None = None,
    ) -> Preview:
        tree = session.printed_tree()
        hidden = frozenset(
            repo_path(path, target.root) for path in session.saved_hidden()
        )
        printed = Document(tree, session.settings, hidden)
        try:
            region = render_region(printed)
            rendered_tree = render_tree(printed.tree, printed.settings)
            dirty = (
                envelope.baseline is None
                or prepare_content(printed, target.root, envelope.baseline)
                != envelope.baseline
            )
        except MarkerError as exc:
            raise PreviewError(422, "curation", str(exc)) from None
        return Preview(
            repo,
            target.resolved.commit,
            target.resolved.tree,
            target.root,
            session.settings,
            len(session.root.walk()),
            len(tree.children),
            rendered_tree,
            region,
            warnings or [],
            envelope.to_dict(),
            _rows(session, reveal),
            document,
            envelope.baseline is not None,
            dirty,
            OPEN_NOTICE
            if opening and dirty and envelope.baseline is not None
            else None,
            target.default_branch,
        )

    async def _symlink_targets(
        self, repo: Repository, snapshot: Snapshot, prefix: str, acquired: bool
    ) -> dict[str, bytes]:
        wanted = dict.fromkeys(
            row.object_id
            for row in snapshot.records
            if row.mode == "120000" and row.path.startswith(prefix)
        )
        limit = self._config.symlink_fetch_limit
        if len(wanted) > limit:
            raise PreviewError(
                422,
                "source_unavailable",
                f"this subtree needs {len(wanted)} symlink targets; "
                f"the service limit is {limit}",
            )
        bodies = await asyncio.gather(
            *(self._blob(repo, snapshot, oid, acquired) for oid in wanted)
        )
        return dict(zip(wanted, bodies, strict=True))


def _snapshot_unavailable() -> PreviewError:
    return PreviewError(
        410,
        "snapshot_unavailable",
        "this snapshot is unavailable; reopen the public default branch "
        "to start a new session",
    )
