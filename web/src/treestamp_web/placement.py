"""Replay a bounded, provisional placement log against the opening snapshot."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from treestamp.document import parse_document
from treestamp.errors import MarkerError
from treestamp.model import path_value, read_path_value
from treestamp.reconcile import Reconciliation
from treestamp.session import TreeSession
from treestamp_web.preview import PreviewError, _display, _rows, parse_op_request

if TYPE_CHECKING:
    from treestamp.model import Node
    from treestamp_web.preview import OpRequest

MAX_DECISIONS = 1024
MAX_EXPANDED = 50_000
_REQUEST_KEYS = {
    "owner",
    "repo",
    "ref",
    "root",
    "document",
    "state",
    "decisions",
    "expanded",
    "reveal",
}


def _path(value: object) -> str:
    try:
        return read_path_value(value)
    except MarkerError as exc:
        raise PreviewError(400, "invalid_placement", str(exc)) from None


@dataclass(frozen=True)
class Decision:
    type: str
    path: str = ""
    replace: bool = False

    @classmethod
    def parse(cls, value: object) -> Decision:
        if not isinstance(value, dict):
            raise PreviewError(400, "invalid_placement", "decision must be an object")
        kind = value.get("type")
        if kind == "skip" and set(value) == {"type"}:
            return cls("skip")
        if kind != "place" or set(value) - {"type", "path", "replace"}:
            raise PreviewError(400, "invalid_placement", "invalid placement decision")
        if "path" not in value or type(value.get("replace", False)) is not bool:
            raise PreviewError(
                400, "invalid_placement", "invalid placement destination"
            )
        return cls("place", _path(value["path"]), value.get("replace", False))

    def apply(self, review: Reconciliation) -> None:
        if self.type == "skip":
            review.skip_current()
            return
        question = review.conflict(self.path)
        if question and not self.replace:
            raise PreviewError(
                409, "placement_conflict", question, extra={"question": question}
            )
        review.place(self.path, replace=self.replace)


@dataclass(frozen=True)
class PlacementRequest:
    opening: OpRequest
    decisions: tuple[Decision, ...]
    expanded: frozenset[str] | None


def parse_placement_request(data: object) -> PlacementRequest:
    if not isinstance(data, dict) or data.keys() - _REQUEST_KEYS:
        raise PreviewError(400, "invalid_placement", "invalid placement request")
    decisions = data.get("decisions")
    if not isinstance(decisions, list) or len(decisions) > MAX_DECISIONS:
        raise PreviewError(
            400,
            "invalid_placement",
            f"decisions must contain at most {MAX_DECISIONS} items",
        )
    expanded = _expanded(data["expanded"]) if "expanded" in data else None
    original = {
        key: value
        for key, value in data.items()
        if key not in {"decisions", "expanded"}
    }
    original["op"] = {"type": "restore"}
    opening = parse_op_request(original)
    if opening.envelope.baseline is None or opening.envelope.revision != 0:
        raise PreviewError(
            400,
            "invalid_placement",
            "placement requires the original document opening state",
        )
    return PlacementRequest(
        opening, tuple(Decision.parse(item) for item in decisions), expanded
    )


def _expanded(value: object) -> frozenset[str]:
    if not isinstance(value, list) or len(value) > MAX_EXPANDED:
        raise PreviewError(400, "invalid_placement", "invalid expanded directory list")
    paths = [_path(path) for path in value]
    if len(paths) != len(set(paths)):
        raise PreviewError(400, "invalid_placement", "duplicate expanded directory")
    return frozenset(paths)


def replay(
    target: Node, request: PlacementRequest
) -> tuple[TreeSession, Reconciliation]:
    envelope = request.opening.envelope
    assert envelope.baseline is not None
    try:
        document = parse_document(envelope.baseline)
        if document is None:
            raise MarkerError("the original document has no treestamp region")
        if document.settings.root != request.opening.root:
            raise MarkerError("document baseline root does not match the request")
        session = TreeSession.restore(target, envelope.curation)
        review = Reconciliation(document.tree, session)
        if not review.total:
            raise MarkerError("the loaded document has no annotations to place")
        for index, decision in enumerate(request.decisions):
            # Undo replays a shorter log, so retain at most one core undo snapshot.
            # This bounds memory instead of retaining a queue copy per decision.
            if index:
                review.restore(replace(review.snapshot(), history=()))
            decision.apply(review)
    except MarkerError as exc:
        raise PreviewError(400, "invalid_placement", str(exc)) from None
    return session, review


def summary(
    review: Reconciliation,
    session: TreeSession,
    *,
    expanded: frozenset[str] | None = None,
    reveal: bool = False,
) -> dict[str, object]:
    browser_state = session.state()
    if expanded is not None:
        browser_state = replace(browser_state, expanded=expanded)
    try:
        browser = TreeSession.restore(session.root, browser_state)
    except MarkerError as exc:
        raise PreviewError(400, "invalid_placement", str(exc)) from None
    current = review.current
    source = (
        None
        if current is None
        else {
            "path": path_value(current.path),
            "key": current.path.encode("utf-8", "surrogateescape").hex(),
            "name": _display(current.name),
            "kind": current.kind,
            "annotation": current.annotation,
        }
    )
    return {
        "current": source,
        "total": review.total,
        "remaining": review.remaining,
        "placed_count": review.placed_count,
        "unplaced": review.unplaced,
        "can_undo": review.can_undo,
        "rows": _rows(browser, reveal),
    }
