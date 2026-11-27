"""JSON values and single-member mutations shared by generated request tests."""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from hypothesis import strategies as st

_TEXT = ("", ".", "..", "/", "a/../b", "sub", "top.txt", "\x00", "\udcff", "f" * 40)
_KEYS = ("git_bytes", "path", "type", "text", "__proto__")


def _json(floats: st.SearchStrategy[float]) -> st.SearchStrategy[object]:
    scalars = st.one_of(
        st.none(),
        st.booleans(),
        st.integers(-(2**64), 2**64),
        floats,
        st.text(max_size=12),
        st.sampled_from(_TEXT),
    )
    return st.recursive(
        scalars,
        lambda children: st.one_of(
            st.lists(children, max_size=4),
            st.dictionaries(
                st.one_of(st.text(max_size=8), st.sampled_from(_KEYS)),
                children,
                max_size=4,
            ),
        ),
        max_leaves=10,
    )


# Python's JSON parser, like the service's, also accepts NaN and Infinity.
json_values = _json(st.floats())
# Standard JSON, as browsers produce and parse it.
strict_json_values = _json(st.floats(allow_nan=False, allow_infinity=False))


def pointers(
    value: object, prefix: tuple[object, ...] = ()
) -> Iterator[tuple[object, ...]]:
    yield prefix
    if isinstance(value, dict):
        for key, child in value.items():
            yield from pointers(child, (*prefix, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from pointers(child, (*prefix, index))


@dataclass(frozen=True)
class Mutation:
    """Change one member of a valid request; the body itself has the pointer ().

    ``replace`` substitutes the value; ``delete`` removes the member (deleting
    the body leaves an empty object); ``add`` gives the object or list at the
    pointer one more member, and replaces a scalar, so no mutation is a no-op.
    """

    pointer: tuple[object, ...]
    kind: str
    value: object

    def apply(self, body: dict[str, Any]) -> Any:
        result: Any = {"body": deepcopy(body)}
        parent: Any = result
        path = ("body", *self.pointer)
        for step in path[:-1]:
            parent = parent[step]
        last = path[-1]
        target = parent[last]
        if self.kind == "delete":
            if self.pointer:
                del parent[last]
            else:
                parent[last] = {}
        elif self.kind == "add" and isinstance(target, dict):
            target["unexpected"] = self.value
        elif self.kind == "add" and isinstance(target, list):
            target.append(self.value)
        else:
            parent[last] = self.value
        return result["body"]


# One value of each JSON type, to swap a member's type outright.
TYPE_CONFUSION = (None, True, -1, 1.5, "", "x", [], {})


def mutations(
    body: dict[str, Any], values: st.SearchStrategy[object] = json_values
) -> st.SearchStrategy[Mutation]:
    # Choosing a depth first keeps the few top-level and envelope fields from
    # being outnumbered by repeated list items.
    by_depth: dict[int, list[tuple[object, ...]]] = {}
    for pointer in pointers(body):
        by_depth.setdefault(len(pointer), []).append(pointer)
    chosen = st.sampled_from(sorted(by_depth)).flatmap(
        lambda depth: st.sampled_from(by_depth[depth])
    )
    return st.builds(
        Mutation,
        chosen,
        st.sampled_from(("replace", "replace", "delete", "add")),
        st.one_of(st.sampled_from(TYPE_CONFUSION), values),
    )
