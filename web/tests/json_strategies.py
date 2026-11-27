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


def _pointers(
    value: object, prefix: tuple[object, ...] = ()
) -> Iterator[tuple[object, ...]]:
    yield prefix
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _pointers(child, (*prefix, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _pointers(child, (*prefix, index))


@dataclass(frozen=True)
class Mutation:
    """Replace, delete, or add one member somewhere in a valid request."""

    pointer: tuple[object, ...]
    kind: str
    value: object

    def apply(self, body: dict[str, Any]) -> Any:
        if not self.pointer:
            return self.value if self.kind == "replace" else body
        result = deepcopy(body)
        parent: Any = result
        for step in self.pointer[:-1]:
            parent = parent[step]
        last = self.pointer[-1]
        if self.kind == "replace":
            parent[last] = self.value
        elif self.kind == "delete":
            del parent[last]
        elif isinstance(parent, dict):
            parent["unexpected"] = self.value
        return result


def mutations(
    body: dict[str, Any], values: st.SearchStrategy[object] = json_values
) -> st.SearchStrategy[Mutation]:
    return st.builds(
        Mutation,
        st.sampled_from(list(_pointers(body))),
        st.sampled_from(("replace", "delete", "add")),
        values,
    )
