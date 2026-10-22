"""Curated printed state with reversible, session-only hidden state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Any

from treestamp.errors import MarkerError
from treestamp.model import (
    Settings,
    initial_tree,
    normalize_annotation,
    path_value,
    read_path_value,
    validate_path,
    validate_tree,
    with_counts,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from treestamp.model import Node

_STATE_KEYS = frozenset(("settings", "expanded", "hidden", "annotations"))


def _ancestors(path: str) -> tuple[str, ...]:
    parts = path.split("/")
    return tuple("/".join(parts[:end]) for end in range(1, len(parts) + 1))


def _path_list(value: object, name: str) -> frozenset[str]:
    if not isinstance(value, list):
        raise MarkerError(f"session state {name} must be an array of paths")
    return frozenset(read_path_value(path) for path in value)


def _settings_value(value: object) -> Settings:
    if not isinstance(value, dict):
        raise MarkerError("session state settings must be an object")
    values: dict[str, Any] = dict(value)
    unknown = values.keys() - asdict(Settings()).keys()
    if unknown:
        raise MarkerError(f"unknown session settings: {', '.join(sorted(unknown))}")
    if "root" in values:
        values["root"] = read_path_value(values["root"])
    return Settings(**values)


def _annotation_map(value: object) -> dict[str, str]:
    if not isinstance(value, list):
        raise MarkerError(
            "session state annotations must be an array of path/text records"
        )
    result: dict[str, str] = {}
    for row in value:
        if not isinstance(row, dict) or set(row) != {"path", "text"}:
            raise MarkerError("annotation record must contain path and text")
        path = read_path_value(row["path"])
        if path in result:
            raise MarkerError(f"duplicate annotation path: {path!r}")
        result[path] = normalize_annotation(row["text"])
    return result


@dataclass(frozen=True)
class SessionState:
    """Everything a session holds that affects future printed output.

    ``expanded`` lists opened non-root directories, which stays small; the
    in-memory collapsed set is its complement within the target's directories.
    ``hidden`` may name untracked paths, exactly like document hiding.
    """

    settings: Settings
    expanded: frozenset[str]
    hidden: frozenset[str]
    annotations: Mapping[str, str]

    def to_dict(self) -> dict[str, object]:
        return {
            "settings": {
                **asdict(self.settings),
                "root": path_value(self.settings.root),
            },
            "expanded": [path_value(path) for path in sorted(self.expanded)],
            "hidden": [path_value(path) for path in sorted(self.hidden)],
            "annotations": [
                {"path": path_value(path), "text": text}
                for path, text in sorted(self.annotations.items())
            ],
        }

    @classmethod
    def from_dict(cls, data: object) -> SessionState:
        """Validate plain data; the caller decodes JSON or other encodings."""
        if not isinstance(data, dict):
            raise MarkerError("session state must be an object")
        unknown = data.keys() - _STATE_KEYS
        if unknown:
            raise MarkerError(
                f"unknown session state keys: {', '.join(sorted(map(str, unknown)))}"
            )
        return cls(
            _settings_value(data.get("settings", {})),
            _path_list(data.get("expanded", []), "expanded"),
            _path_list(data.get("hidden", []), "hidden"),
            _annotation_map(data.get("annotations", [])),
        )


class TreeSession:
    """Hold a fixed complete snapshot and curate its visible rows.

    Hidden annotations and descendant layouts remain in this object after a write.
    Only ``printed_tree`` and ``saved_hidden`` belong in a document.
    """

    def __init__(
        self,
        target: Node,
        settings: Settings,
        tree: Node | None = None,
        hidden: frozenset[str] = frozenset(),
    ) -> None:
        self._bind(target, settings)
        printed = tree if tree is not None else initial_tree(target, settings)
        rows = {node.path: node for node in (printed, *printed.walk())}
        self.collapsed = self._initial_collapsed(rows)
        for path in hidden:
            validate_path(path)
        self.hidden = set(hidden)
        self.annotations = {
            path: normalize_annotation(node.annotation)
            for path, node in rows.items()
            if node.annotation
        }

    def _bind(self, target: Node, settings: Settings) -> None:
        validate_tree(target, full=True)
        self.root = target
        self.settings = settings
        self._nodes = {node.path: node for node in (target, *target.walk())}
        self.show_hidden = False

    def _directories(self) -> set[str]:
        return {path for path, node in self._nodes.items() if node.is_dir and path}

    @classmethod
    def restore(cls, target: Node, state: SessionState) -> TreeSession:
        """Rebuild a session against the same target it was captured from."""
        session = cls.__new__(cls)
        session._bind(target, state.settings)
        directories = session._directories()
        for path in state.expanded:
            if path not in directories:
                raise MarkerError(f"not a tracked directory: {path!r}")
        for path in state.hidden:
            validate_path(path)
        annotations: dict[str, str] = {}
        for path, text in state.annotations.items():
            normalized = session.normalize_entry(path)
            text = normalize_annotation(text)
            if text:
                annotations[normalized] = text
        session.collapsed = directories - state.expanded
        session.hidden = set(state.hidden)
        session.annotations = annotations
        return session

    def state(self) -> SessionState:
        """Capture settings, opened directories, hidden paths, and annotations."""
        return SessionState(
            self.settings,
            frozenset(self._directories() - self.collapsed),
            frozenset(self.hidden),
            dict(self.annotations),
        )

    def _initial_collapsed(self, rows: dict[str, Node]) -> set[str]:
        expanded = {
            path for path, node in rows.items() if node.is_dir and node.children
        }
        expanded.add("")
        return {
            path
            for path, node in self._nodes.items()
            if node.is_dir and path not in expanded
        }

    @property
    def show_counts(self) -> bool:
        return self.settings.show_counts

    @show_counts.setter
    def show_counts(self, value: bool) -> None:
        self.settings = replace(self.settings, show_counts=value)

    def normalize_entry(self, path: str) -> str:
        normalized = "" if path == "." else path
        if normalized not in self._nodes:
            raise MarkerError(f"not a tracked entry: {path!r}")
        return normalized

    def _directory_path(self, path: str) -> str:
        normalized = self.normalize_entry(path)
        if not self._nodes[normalized].is_dir:
            raise MarkerError(f"not a tracked directory: {path!r}")
        return normalized

    def is_hidden(self, path: str) -> bool:
        normalized = self.normalize_entry(path)
        return bool(normalized and self.hidden.intersection(_ancestors(normalized)))

    def hide(self, path: str) -> None:
        normalized = self.normalize_entry(path)
        if normalized:
            self.hidden.add(normalized)

    def unhide(self, path: str) -> None:
        self.hidden.difference_update(_ancestors(self.normalize_entry(path)))

    def unhide_all(self) -> None:
        """Remove every hiding decision while preserving expansion and annotations."""
        self.hidden.clear()

    def toggle_hidden(self, path: str) -> None:
        if self.is_hidden(path):
            self.unhide(path)
        else:
            self.hide(path)

    def collapse(self, path: str) -> None:
        normalized = self._directory_path(path)
        if normalized:
            self.collapsed.add(normalized)

    def expand(self, path: str) -> None:
        self.collapsed.discard(self._directory_path(path))

    def toggle(self, path: str) -> None:
        normalized = self._directory_path(path)
        if normalized in self.collapsed:
            self.expand(normalized)
        else:
            self.collapse(normalized)

    def set_annotation(self, path: str, text: str) -> None:
        normalized = self.normalize_entry(path)
        text = normalize_annotation(text)
        if text:
            self.annotations[normalized] = text
        else:
            self.annotations.pop(normalized, None)

    def immediate_counts(self, path: str) -> tuple[int, int]:
        node = self._nodes[self._directory_path(path)]
        files = sum(not child.is_dir for child in node.children)
        return files, len(node.children) - files

    def printed_tree(self) -> Node:
        def visit(node: Node) -> Node:
            children: tuple[Node, ...] = ()
            if node.is_dir and node.path not in self.collapsed:
                children = tuple(
                    visit(child)
                    for child in node.children
                    if not self.is_hidden(child.path)
                )
            curated = replace(
                node,
                children=children,
                annotation=self.annotations.get(node.path, ""),
            )
            return with_counts(curated, node, self.settings)

        return visit(self.root)

    def saved_hidden(self) -> frozenset[str]:
        printed = self.printed_tree()
        expanded = {
            node.path
            for node in (printed, *printed.walk())
            if node.is_dir and (not node.path or node.children)
        }
        return frozenset(
            path for path in self.hidden if path.rpartition("/")[0] in expanded
        )

    def draft_signature(self) -> object:
        """Compare saved meaning even when a visible row cannot yet be printed."""
        return (
            self.printed_tree(),
            self.settings,
            self.saved_hidden(),
        )

    def visible_rows(self) -> list[tuple[Node, int]]:
        rows: list[tuple[Node, int]] = []

        def visit(node: Node, depth: int) -> None:
            if not self.show_hidden and self.is_hidden(node.path):
                return
            rows.append((node, depth))
            if node.path not in self.collapsed:
                for child in node.children:
                    visit(child, depth + 1)

        visit(self.root, 0)
        return rows

    def is_visibly_collapsed(self, path: str) -> bool:
        normalized = self._directory_path(path)
        node = self._nodes[normalized]
        return bool(normalized) and (
            normalized in self.collapsed
            or not any(
                self.show_hidden or not self.is_hidden(child.path)
                for child in node.children
            )
        )

    def hidden_stats(self) -> tuple[int, int]:
        hidden = [node for node in self.root.walk() if self.is_hidden(node.path)]
        files = sum(not node.is_dir for node in hidden)
        return files, len(hidden) - files
