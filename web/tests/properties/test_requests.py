"""Request parsing handles arbitrary and nearly valid data without internal errors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from treestamp.document import Document, render_region
from treestamp.errors import MarkerError
from treestamp.model import KIND_DIR, KIND_FILE, Node, Settings
from treestamp.session import SessionState
from treestamp_web.export import export_svg
from treestamp_web.placement import parse_placement_request
from treestamp_web.preview import (
    Envelope,
    PreviewError,
    parse_op_request,
    parse_preview_body,
    parse_request,
)

from .strategies import lenient_json_values, mutations


def _request_body() -> dict[str, Any]:
    """A parser input needs no repository acquisition or server cache."""
    source = {
        "owner": "o",
        "repo": "r",
        "commit": "a" * 40,
        "root": ".",
        "document": "README.md",
    }
    settings = Settings()
    tree = Node(".", "", KIND_DIR, (Node("file", "file", KIND_FILE),))
    baseline = render_region(Document(tree, settings)).encode("utf-8")
    state = SessionState(settings, frozenset(), frozenset(), {})
    envelope = Envelope(state, source, baseline, "opening")
    return {
        "owner": source["owner"],
        "repo": source["repo"],
        "ref": source["commit"],
        "root": source["root"],
        "document": source["document"],
        "state": envelope.to_dict(),
        "reveal": False,
    }


def _domain_rejection(
    call: Callable[[object], object], value: object, *, allow_marker_error: bool = False
) -> None:
    try:
        call(value)
    except PreviewError as exc:
        assert 400 <= exc.status < 500, exc.status
    except MarkerError:
        assert allow_marker_error, "a request parser leaked a MarkerError"


@given(lenient_json_values)
def test_request_parsers_handle_arbitrary_json_without_internal_errors(
    value: object,
) -> None:
    for parse in (parse_op_request, parse_placement_request, parse_preview_body):
        _domain_rejection(parse, value)
    _domain_rejection(export_svg, value, allow_marker_error=True)


@given(
    st.dictionaries(
        st.text(max_size=8), st.one_of(st.none(), st.text(max_size=40)), max_size=4
    )
)
def test_query_parser_handles_arbitrary_parameters_without_internal_errors(
    params: dict[str, str | None],
) -> None:
    _domain_rejection(parse_request, params)


@given(st.data())
def test_nearly_valid_requests_do_not_leak_internal_errors(data: st.DataObject) -> None:
    opening = _request_body()
    operation = {
        **opening,
        "op": data.draw(
            st.sampled_from(
                (
                    {"type": "restore"},
                    {"type": "toggle", "path": "file"},
                    {
                        "type": "annotate",
                        "path": {"git_bytes": "ff"},
                        "text": "<img src=x>",
                    },
                )
            )
        ),
    }
    placement = {
        **opening,
        "decisions": data.draw(
            st.sampled_from(
                ([], [{"type": "skip"}], [{"type": "place", "path": "file"}])
            )
        ),
    }
    for parse, valid in (
        (parse_op_request, operation),
        (parse_placement_request, placement),
    ):
        # Establish that mutations start inside the accepted parser domain.
        parse(valid)
        _domain_rejection(parse, data.draw(mutations(valid)).apply(valid))
