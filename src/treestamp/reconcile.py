"""One-time, manual placement of annotations left behind by removed rows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from treestamp.errors import MarkerError

if TYPE_CHECKING:
    from treestamp.model import Node
    from treestamp.session import TreeSession


@dataclass(frozen=True)
class _Decisions:
    pending: tuple[str, ...]
    skipped: tuple[str, ...]
    placed: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class _Transfer:
    destination: str
    annotation: str
    displaced: str


@dataclass(frozen=True)
class _Action:
    before: _Decisions
    message: str
    transfers: tuple[_Transfer, ...] = ()
    collapsed_before: frozenset[str] = frozenset()
    collapsed_after: frozenset[str] = frozenset()
    hidden_before: frozenset[str] = frozenset()
    hidden_after: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ReconciliationState:
    """Bookkeeping captured alongside the editor's transactional draft state."""

    decisions: _Decisions
    history: tuple[_Action, ...]


def _inside(path: str, directory: str) -> bool:
    return path.startswith(directory + "/")


class Reconciliation:
    """Place or skip removed annotations before ordinary document editing.

    Removed directories group their annotated descendants even without their own
    annotation. Placing a directory carries compatible pending descendants by
    their complete relative paths; one undo reverses that entire decision.
    """

    def __init__(self, loaded: Node, session: TreeSession) -> None:
        self.session = session
        removed = {
            node.path: node
            for node in (loaded, *loaded.walk())
            if not self._survives(node)
        }
        annotated = {path for path, node in removed.items() if node.annotation}
        groups = self._groups(removed, annotated)
        self._sources = {
            path: node
            for path, node in removed.items()
            if path in annotated or path in groups
        }
        self._pending = list(self._sources)
        self.skipped: list[str] = []
        self.placed: dict[str, str] = {}
        self._history: list[_Action] = []

    @staticmethod
    def _groups(removed: dict[str, Node], annotated: set[str]) -> set[str]:
        groups: set[str] = set()
        for path in annotated:
            group = None
            while path := path.rpartition("/")[0]:
                node = removed.get(path)
                if node is not None and node.is_dir:
                    group = path
            if group is not None:
                groups.add(group)
        return groups

    def _survives(self, node: Node) -> bool:
        entry = self.session.entry(node.path)
        return entry is not None and entry.kind == node.kind

    @property
    def current(self) -> Node | None:
        return self._sources[self._pending[0]] if self._pending else None

    @property
    def total(self) -> int:
        return sum(bool(node.annotation) for node in self._sources.values())

    @property
    def remaining(self) -> int:
        return sum(bool(self._sources[path].annotation) for path in self._pending)

    @property
    def placed_count(self) -> int:
        return sum(bool(self._sources[path].annotation) for path in self.placed)

    @property
    def unplaced(self) -> int:
        return self.total - self.placed_count

    @property
    def can_undo(self) -> bool:
        return bool(self._history)

    def _decisions(self) -> _Decisions:
        return _Decisions(
            tuple(self._pending), tuple(self.skipped), tuple(self.placed.items())
        )

    def _restore_decisions(self, state: _Decisions) -> None:
        self._pending = list(state.pending)
        self.skipped = list(state.skipped)
        self.placed = dict(state.placed)

    def snapshot(self) -> ReconciliationState:
        return ReconciliationState(self._decisions(), tuple(self._history))

    def restore(self, state: ReconciliationState) -> None:
        self._restore_decisions(state.decisions)
        self._history = list(state.history)

    def _source(self) -> Node:
        source = self.current
        if source is None:
            raise MarkerError("No note is awaiting a decision.")
        return source

    def skip_current(self) -> None:
        source = self._source()
        self._history.append(_Action(self._decisions(), f"Undid skip: {source.path}"))
        self._pending.pop(0)
        if source.annotation:
            self.skipped.append(source.path)

    def _destination(self, destination: str) -> str:
        source = self._source()
        destination = self.session.normalize_entry(destination)
        entry = self.session.entry(destination)
        assert entry is not None
        if source.is_dir != entry.is_dir:
            kind = "directory" if source.is_dir else "file"
            raise MarkerError(f"Choose a {kind} for {source.path!r}.")
        return destination

    def _holder(self, destination: str) -> str | None:
        return next(
            (
                source
                for source, path in self.placed.items()
                if path == destination and self._sources[source].annotation
            ),
            None,
        )

    def conflict(self, destination: str) -> str | None:
        destination = self._destination(destination)
        source = self._source()
        if not source.annotation:
            return None
        holder = self._holder(destination)
        shown = destination or "."
        if holder is not None:
            return (
                f"Replace the note placed on {shown}? "
                f"{holder} will return to the review queue."
            )
        existing = self.session.annotations.get(destination, "")
        if existing and existing != source.annotation:
            return f"Replace the note on {shown}? Undo will restore it."
        return None

    def _reveal(self, destination: str) -> None:
        self.session.unhide(destination)
        parts = destination.split("/")
        for end in range(1, len(parts)):
            self.session.expand("/".join(parts[:end]))

    def _descendants(self, source: Node, destination: str) -> list[tuple[str, str]]:
        if not source.is_dir:
            return []
        pairs: list[tuple[str, str]] = []
        for path in self._pending:
            if not _inside(path, source.path):
                continue
            node = self._sources[path]
            relative = path[len(source.path) + 1 :]
            target = f"{destination}/{relative}" if destination else relative
            if node.annotation and self._compatible(node, target):
                pairs.append((path, target))
        return pairs

    def _compatible(self, source: Node, destination: str) -> bool:
        target = self.session.entry(destination)
        return (
            target is not None
            and target.kind == source.kind
            and self._holder(destination) is None
            and self.session.annotations.get(destination, "") in ("", source.annotation)
        )

    def _transfer(self, source: str, destination: str) -> _Transfer | None:
        node = self._sources[source]
        transfer = None
        if node.annotation:
            holder = self._holder(destination)
            if holder is not None:
                del self.placed[holder]
                self._pending.append(holder)
            transfer = _Transfer(
                destination,
                node.annotation,
                self.session.annotations.get(destination, ""),
            )
            self.session.set_annotation(destination, node.annotation)
            self._reveal(destination)
        self._pending.remove(source)
        self.placed[source] = destination
        return transfer

    def _prune_groups(self) -> None:
        annotated = [path for path in self._pending if self._sources[path].annotation]
        self._pending = [
            path
            for path in self._pending
            if self._sources[path].annotation
            or any(_inside(p, path) for p in annotated)
        ]

    def place(self, destination: str, *, replace: bool = False) -> str:
        source = self._source()
        destination = self._destination(destination)
        if not replace and self.conflict(destination) is not None:
            raise MarkerError("Placement would replace an existing note.")
        before = self._decisions()
        collapsed = frozenset(self.session.collapsed)
        hidden = frozenset(self.session.hidden)
        pairs = [(source.path, destination), *self._descendants(source, destination)]
        transfers = tuple(
            transfer
            for path, target in pairs
            if (transfer := self._transfer(path, target)) is not None
        )
        self._prune_groups()
        self._history.append(
            _Action(
                before=before,
                message=f"Undid placement: {source.path}",
                transfers=transfers,
                collapsed_before=collapsed,
                collapsed_after=frozenset(self.session.collapsed),
                hidden_before=hidden,
                hidden_after=frozenset(self.session.hidden),
            )
        )
        carried = len(pairs) - 1
        suffix = f" and {carried} descendant notes" if carried else ""
        return (
            f"Placed {source.path} → {destination or '.'}{suffix}; "
            f"{self.remaining} remain."
        )

    def undo(self) -> str:
        if not self._history:
            return "Nothing to undo."
        action = self._history.pop()
        edited = False
        for transfer in action.transfers:
            current = self.session.annotations.get(transfer.destination, "")
            if current == transfer.annotation:
                self.session.set_annotation(transfer.destination, transfer.displaced)
            else:
                edited = True
        if action.transfers and not edited:
            if self.session.collapsed == action.collapsed_after:
                self.session.collapsed = set(action.collapsed_before)
            if self.session.hidden == action.hidden_after:
                self.session.hidden = set(action.hidden_before)
        self._restore_decisions(action.before)
        return action.message
