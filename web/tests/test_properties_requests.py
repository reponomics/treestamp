"""Generated hosted requests: domain rejections, accepted constraints, and state.

Parsers are checked on their own, then whole requests go through the HTTP
application. Each service example builds a fresh application, so cache and rate
limiter state never carry over. Upstream responses come from a local fixture
repository, recorded once per module; nothing reaches GitHub.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from hypothesis import event, given
from hypothesis import strategies as st

from treestamp.document import Document, render_region
from treestamp.errors import MarkerError
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings, read_path_value, repo_path
from treestamp.session import TreeSession
from treestamp_web.app import create_app
from treestamp_web.export import export_svg
from treestamp_web.localgit import FakeGitHub, FakeOptions, LocalRepository
from treestamp_web.placement import parse_placement_request
from treestamp_web.preview import (
    Envelope,
    PreviewError,
    parse_op_request,
    parse_preview_body,
    parse_request,
)

from .conftest import Clock, Repo, make_config
from .json_strategies import (
    TYPE_CONFUSION,
    Mutation,
    json_values,
    mutations,
    pointers,
)

Key = tuple[str, str, tuple[tuple[str, str], ...], str]
Recorded = tuple[int, dict[str, str], bytes]


@dataclass
class Upstream:
    """A fixture repository whose GitHub responses are computed once."""

    fake: FakeGitHub = field(repr=False)
    commit: str
    paths: frozenset[str]
    directories: frozenset[str]
    objects: tuple[str, ...]  # older commits and object ids the fake would serve
    responses: dict[Key, Recorded] = field(default_factory=dict, repr=False)

    def transport(self, calls: list[str]) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            key = (
                request.method,
                request.url.path,
                tuple(sorted(request.url.params.multi_items())),
                request.headers.get("accept", ""),
            )
            if key not in self.responses:
                self.responses[key] = self.fake.respond(
                    request.url.path,
                    dict(request.url.params),
                    request.headers.get("accept", ""),
                    method=request.method,
                )
            status, headers, body = self.responses[key]
            return httpx.Response(status, headers=headers, content=body)

        return httpx.MockTransport(handler)


def _build(path: Path) -> Repo:
    """Every entry kind, a byte name, and notes whose paths later move."""
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    repo = Repo(path)
    repo.git("config", "user.email", "test@example.invalid")
    repo.git("config", "user.name", "Test")
    for rel in ("sub/deep/leaf.txt", "sub/other.txt", "top.txt", 'quote "me".txt'):
        repo.write(rel, "x")
    for rel in ("old/a.py", "old/b.py", "README.md"):
        repo.write(rel)
    (path / "link").symlink_to("sub/deep")
    repo.git("add", "-A")
    blob = repo.git("hash-object", "-w", "--stdin", input_bytes=b"raw").strip()
    repo.git("update-index", "--add", "--cacheinfo", f"100644,{blob},byte\udcff.txt")
    session = TreeSession(capture_snapshot(path).tree, Settings())
    session.expand("old")
    session.set_annotation("old/a.py", "first <b>note</b>")
    session.set_annotation("old/b.py", "second note")
    session.set_annotation("top.txt", "kept note")
    region = render_region(Document(session.printed_tree(), Settings()))
    repo.write("README.md", f"# Fixture\n\n{region}\nTail.\n")
    repo.git("add", "README.md")
    repo.commit("annotated", stage=False)
    repo.git("mv", "old", "new")
    repo.commit("moved", stage=False)
    return repo


@pytest.fixture(scope="module")
def upstream(tmp_path_factory: pytest.TempPathFactory) -> Upstream:
    repo = _build(tmp_path_factory.mktemp("properties") / "repo")
    local = LocalRepository(repo.path)
    commit = local.resolve("HEAD")
    assert commit is not None
    tree = local.tree_id(commit)
    assert tree is not None
    records = local.records(tree) or []
    history = repo.git("rev-list", "HEAD").split()
    return Upstream(
        FakeGitHub(local, FakeOptions(limit=1_000_000)),
        commit,
        frozenset(row.path for row in records),
        frozenset(row.path for row in records if row.type == "tree"),
        (*history[1:], tree, *(row.object_id for row in records)),
    )


@contextmanager
def fresh_client(
    upstream: Upstream, calls: list[str], clock: Clock | None = None
) -> Iterator[TestClient]:
    # Rejected requests consume rate-limit tokens by design; 0 disables limits.
    config = make_config(rate_limit_per_minute=0, op_rate_limit_per_minute=0)
    transport = upstream.transport(calls)
    app = create_app(config, transport=transport, clock=clock or Clock())
    with TestClient(app) as client:
        yield client


def opened(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/preview", json={"url": "o/r", "document": "README.md"})
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    assert data["placement"], "the fixture must offer notes to place"
    return data


@pytest.fixture(scope="module")
def opening(upstream: Upstream) -> dict[str, Any]:
    with fresh_client(upstream, []) as client:
        return opened(client)


VALID_OPERATIONS = (
    {"type": "restore"},
    {"type": "reset"},
    {"type": "toggle", "path": "sub"},
    {"type": "expand", "path": "new"},
    {"type": "hide", "path": "top.txt"},
    {"type": "unhide_all"},
    {
        "type": "annotate",
        "path": {"git_bytes": "62797465ff2e747874"},
        "text": "<img src=x>",
    },
)
VALID_DECISIONS = ([], [{"type": "skip"}], [{"type": "place", "path": "new"}])


def operation_body(
    opening: dict[str, Any], operation: dict[str, Any]
) -> dict[str, Any]:
    return {
        "owner": "o",
        "repo": "r",
        "ref": opening["ref"]["commit"],
        "root": opening["root"],
        "document": opening["document"],
        "state": opening["state"],
        "reveal": False,
        "op": operation,
    }


def placement_body(opening: dict[str, Any], decisions: list[Any]) -> dict[str, Any]:
    body = operation_body(opening, {})
    del body["op"]
    return {**body, "decisions": decisions}


def _domain_rejection(
    call: Callable[[object], object], value: object, *, document_error: bool = False
) -> None:
    """Expect a result or a 4xx PreviewError; MarkerError only where documented.

    Over HTTP an escaped MarkerError becomes 422 ``curation``, which request
    parsers must not produce; SVG export reports document errors that way.
    """
    try:
        call(value)
    except PreviewError as exc:
        assert 400 <= exc.status < 500, exc.status
    except MarkerError:
        assert document_error, "a request parser leaked a MarkerError"


@given(json_values)
def test_request_parsers_turn_arbitrary_json_into_domain_rejections(
    value: object,
) -> None:
    for parse in (parse_op_request, parse_placement_request, parse_preview_body):
        _domain_rejection(parse, value)
    _domain_rejection(export_svg, value, document_error=True)


@given(
    st.dictionaries(
        st.text(max_size=8), st.one_of(st.none(), st.text(max_size=40)), max_size=4
    )
)
def test_query_parser_turns_arbitrary_parameters_into_domain_rejections(
    params: dict[str, str | None],
) -> None:
    _domain_rejection(parse_request, params)


@given(st.data())
def test_parsers_reject_mutated_requests_with_domain_errors(
    opening: dict[str, Any], data: st.DataObject
) -> None:
    operation = operation_body(opening, data.draw(st.sampled_from(VALID_OPERATIONS)))
    _domain_rejection(
        parse_op_request, data.draw(mutations(operation)).apply(operation)
    )
    placement = placement_body(opening, data.draw(st.sampled_from(VALID_DECISIONS)))
    _domain_rejection(
        parse_placement_request, data.draw(mutations(placement)).apply(placement)
    )


def _cache(client: TestClient) -> object:
    items = client.app.state.service._snapshots._items
    return [
        (key, e.expires, list(e.snapshot.records), dict(e.snapshot.blobs))
        for key, e in items.items()
    ]


def _post(client: TestClient, endpoint: str, body: object) -> httpx.Response:
    content = json.dumps(body, allow_nan=True).encode("utf-8", "surrogatepass")
    return client.post(
        endpoint, content=content, headers={"content-type": "application/json"}
    )


def _check_accepted(upstream: Upstream, request: Any, data: dict[str, Any]) -> None:
    state = data["state"]
    assert data["ref"]["commit"] == upstream.commit
    assert state["source"] == request["state"]["source"]
    assert state["source"]["commit"] == upstream.commit
    root = read_path_value(state["source"]["root"])

    def tracked(value: object, within: frozenset[str] = upstream.paths) -> bool:
        path = read_path_value(value)
        return path == "" or repo_path(path, root) in within

    curation = state["curation"]
    assert all(tracked(row["path"]) for row in data["rows"])
    assert all(tracked(path, upstream.directories) for path in curation["expanded"])
    assert all(tracked(note["path"]) for note in curation["annotations"])
    transported = Envelope.from_dict(json.loads(json.dumps(state)))
    assert transported.to_dict() == state


ENDPOINTS = {"/api/op": operation_body, "/api/placement": placement_body}


def _exercise(
    client: TestClient,
    clock: Clock,
    upstream: Upstream,
    calls: list[str],
    endpoint: str,
    valid: dict[str, Any],
    mutated: object,
    accepted: dict[str, Any],
) -> int:
    """Post one mutated request after its valid original was accepted."""
    # Time passes between requests, so a rejected request that renewed the
    # snapshot's lease would change its expiry.
    clock.now += 1
    cache, fetched = _cache(client), len(calls)
    response = _post(client, endpoint, mutated)
    assert len(calls) == fetched, "an edit request reached GitHub"
    if response.status_code == 200:
        _check_accepted(upstream, mutated, response.json())
        return response.status_code
    # The fixture's entries are all representable, so 422 would be an
    # unexpected failure mapped to a curation error.
    assert response.status_code in (400, 409, 410), response.text
    assert set(response.json()["error"]) >= {"code", "message"}
    assert _cache(client) == cache
    assert _post(client, endpoint, valid).json() == accepted
    return response.status_code


@given(st.data())
def test_mutated_requests_are_rejected_without_changing_service_state(
    upstream: Upstream, opening: dict[str, Any], data: st.DataObject
) -> None:
    endpoint = data.draw(st.sampled_from(sorted(ENDPOINTS)))
    choices = VALID_OPERATIONS if endpoint == "/api/op" else VALID_DECISIONS
    valid = ENDPOINTS[endpoint](opening, data.draw(st.sampled_from(choices)))
    # Several independent single-field mutations share one fresh application.
    variants = data.draw(st.lists(mutations(valid), min_size=1, max_size=6))
    calls: list[str] = []
    clock = Clock()
    with fresh_client(upstream, calls, clock) as client:
        opened(client)
        accepted = _post(client, endpoint, valid)
        assert accepted.status_code == 200, accepted.text
        for variant in variants:
            mutated = variant.apply(valid)
            status = _exercise(
                client,
                clock,
                upstream,
                calls,
                endpoint,
                valid,
                mutated,
                accepted.json(),
            )
            event(f"{endpoint} {status}")


@pytest.mark.parametrize(
    ("endpoint", "choice"),
    [("/api/op", {"type": "toggle", "path": "sub"}), ("/api/placement", [])],
)
def test_type_swaps_of_every_member_end_in_rejection_or_accepted_constraints(
    upstream: Upstream, opening: dict[str, Any], endpoint: str, choice: object
) -> None:
    """A complete sweep of type swaps, which random mutation reaches slowly."""
    valid = ENDPOINTS[endpoint](opening, choice)
    calls: list[str] = []
    clock = Clock()
    with fresh_client(upstream, calls, clock) as client:
        opened(client)
        accepted = _post(client, endpoint, valid).json()
        for pointer in pointers(valid):
            for value in TYPE_CONFUSION:
                mutated = Mutation(pointer, "replace", value).apply(valid)
                _exercise(
                    client, clock, upstream, calls, endpoint, valid, mutated, accepted
                )


def pinned_commits(upstream: Upstream) -> st.SearchStrategy[str]:
    random = st.text("0123456789abcdef", min_size=40, max_size=40)
    return st.one_of(st.sampled_from(upstream.objects), random).filter(
        lambda commit: commit != upstream.commit
    )


@given(st.data())
def test_fabricated_commits_never_authorize_github_reads(
    upstream: Upstream, opening: dict[str, Any], data: st.DataObject
) -> None:
    commit = data.draw(pinned_commits(upstream))
    calls: list[str] = []
    with fresh_client(upstream, calls) as client:
        opened(client)
        fetched = len(calls)
        for endpoint, body in (
            ("/api/op", operation_body(opening, {"type": "restore"})),
            ("/api/placement", placement_body(opening, [])),
        ):
            forged = deepcopy(body)
            forged["ref"] = commit
            forged["state"]["source"]["commit"] = commit
            response = _post(client, endpoint, forged)
            assert response.status_code == 410, response.text
            assert response.json()["error"]["code"] == "snapshot_unavailable"
        assert len(calls) == fetched
        pinned = {"owner": "o", "repo": "r", "ref": commit}
        assert client.post("/api/preview", json=pinned).status_code == 410
        assert client.get("/api/browse", params=pinned).status_code == 410
        # Only repository metadata and default-branch resolution are allowed.
        assert all(commit not in url for url in calls[fetched:])
        assert not any(
            "/git/trees" in url or "/git/blobs" in url for url in calls[fetched:]
        )
