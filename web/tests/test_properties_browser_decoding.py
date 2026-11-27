"""Generated browser decoding cases against the page's own logic.js and draft.js.

Hypothesis generates the cases here; a persistent Node worker
(tests/js/property_worker.mjs) evaluates them with the real modules, so no
decoder is reimplemented in Python. Requires Node 24 or later: skipped locally
without it, and a failure when CI is set.
"""

from __future__ import annotations

import base64
import json
import os
import queue
import re
import shutil
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from .json_strategies import mutations as _mutations
from .json_strategies import strict_json_values

WORKER = Path(__file__).parent / "js" / "property_worker.mjs"
REQUIRED_NODE = 24
RESPONSE_TIMEOUT = 60.0  # seconds; a process timeout for hangs, not a deadline
ORIGIN = "https://treestamp.invalid"
COMMIT = "a" * 40


def _node() -> str:
    node = shutil.which("node")
    version = ""
    if node:
        version = subprocess.run(
            [node, "--version"], capture_output=True, encoding="utf-8", check=False
        ).stdout
    match = re.match(r"v(\d+)\.", version)
    if match and int(match[1]) >= REQUIRED_NODE:
        return node
    reason = f"Node {REQUIRED_NODE} or later is required for browser decoding cases"
    if os.environ.get("CI"):
        pytest.fail(reason)
    pytest.skip(reason)


class Worker:
    """One Node process; restarted if it exits, failed on a hang."""

    def __init__(self, node: str) -> None:
        self._node = node
        self._start()

    def _start(self) -> None:
        self._process = subprocess.Popen(
            [self._node, str(WORKER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            encoding="utf-8",
        )
        self._lines: queue.Queue[str] = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        assert self._process.stdout is not None
        for line in self._process.stdout:
            self._lines.put(line)
        self._lines.put("")  # the worker exited

    def call(self, name: str, *args: object) -> dict[str, Any]:
        assert self._process.stdin is not None
        request = json.dumps(
            {"call": name, "args": args}, ensure_ascii=True, allow_nan=False
        )
        try:
            self._process.stdin.write(request + "\n")
            self._process.stdin.flush()
            line = self._lines.get(timeout=RESPONSE_TIMEOUT)
        except (BrokenPipeError, queue.Empty):
            line = ""
        if not line:
            self.close()
            self._start()
            raise AssertionError(f"the Node worker did not answer {name}")
        response: dict[str, Any] = json.loads(line)
        assert response.pop("prototype"), f"{name} modified Object.prototype"
        return response

    def value(self, name: str, *args: object) -> Any:
        """Return the call's result; any exception is a failure."""
        response = self.call(name, *args)
        assert response["ok"], f"{name} threw {response['error']}"
        return response["value"]

    def close(self) -> None:
        self._process.kill()
        self._process.wait()


@pytest.fixture(scope="module")
def worker() -> Iterator[Worker]:
    running = Worker(_node())
    yield running
    running.close()


def controlled(response: dict[str, Any]) -> bool:
    """A result, or an Error with a user-facing message; TypeError is a failure."""
    return response["ok"] or response["error"]["type"] == "Error"


def fragment(state: object) -> str:
    """Encode a state as the page does: JSON, UTF-8, then unpadded base64url."""
    data = json.dumps(state, ensure_ascii=True).encode("ascii")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def captured_state(worker: Worker) -> dict[str, Any]:
    """A service-shaped captured session for the link's own owner, repo, and commit."""
    state: dict[str, Any] = worker.value("example")["state"]
    state["source"].update(owner="o", repo="r", commit=COMMIT)
    return state


def mutations(body: dict[str, Any]) -> st.SearchStrategy[Any]:
    return _mutations(body, strict_json_values)


# Identity domain: JSON without -0 or non-finite numbers; integers stay within
# the range both Python and JavaScript represent exactly. Lone surrogates are in.
_SAFE = 2**53 - 1
identity_values = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(-_SAFE, _SAFE),
        st.text(st.characters(codec=None), max_size=8),
        st.sampled_from(("\ud800", "\udfff\ud800", "\U0001f600", "__proto__")),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(
            st.one_of(st.text(max_size=6), st.just("__proto__")), children, max_size=4
        ),
    ),
    max_leaves=12,
)

base64ish = st.one_of(
    st.text(max_size=40),
    st.text("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=+/"),
    st.binary(max_size=60).map(
        lambda data: base64.urlsafe_b64encode(data).decode().rstrip("=")
    ),
    strict_json_values.map(fragment),
)


@given(identity_values.map(lambda value: {"value": value}))
def test_supported_states_survive_the_fragment(worker: Worker, state: Any) -> None:
    assert worker.value("roundTripState", state) == state
    route = worker.value("parseRoute", f"/o/r@{COMMIT}", "#s=" + fragment(state))
    assert route == {"owner": "o", "repo": "r", "sha": COMMIT, "saved": state}


@given(base64ish)
def test_arbitrary_fragments_decode_to_objects_or_null(
    worker: Worker, text: str
) -> None:
    decoded = worker.value("decodeState", text)
    assert decoded is None or isinstance(decoded, dict)


@given(
    st.one_of(
        st.text(max_size=30), st.from_regex(r"\A/[^/@]+/[^/@]+(@[0-9a-f]{40})?/?\Z")
    ),
    st.one_of(st.text(max_size=20), base64ish.map("#s=".__add__)),
)
def test_routes_parse_without_exceptions(worker: Worker, path: str, hash: str) -> None:
    route = worker.value("parseRoute", path, hash)
    if route is not None:
        assert route["sha"] is None or re.fullmatch("[0-9a-f]{40}", route["sha"])
        assert route["saved"] is None or isinstance(route["saved"], dict)


@given(st.text(max_size=40))
def test_queries_accept_only_document_options(worker: Worker, query: str) -> None:
    response = worker.call("valuesFromQuery", query)
    assert controlled(response), response
    if response["ok"]:
        assert set(response["value"]) <= {"root", "document"}


def _mutated_state(worker: Worker, data: st.DataObject) -> object:
    state = captured_state(worker)
    return data.draw(
        st.one_of(st.just(state), mutations(state).map(lambda m: m.apply(state)))
    )


@given(st.data())
def test_links_with_malformed_sessions_never_throw_at_startup(
    worker: Worker, data: st.DataObject
) -> None:
    saved = _mutated_state(worker, data)
    shown = worker.value("startup", f"/o/r@{COMMIT}", "#s=" + fragment(saved))
    if saved == captured_state(worker):
        assert shown is not None, "a service-shaped session must be accepted"


_locations = st.fixed_dictionaries(
    {
        "pathname": st.sampled_from(
            ("/", "/o/r", "/O/R/", "/other/repo", f"/o/r@{COMMIT}")
        ),
        "search": st.sampled_from(("", "?root=.")),
        "hash": st.sampled_from(("", "#s=e30")),
    }
)


@given(st.data(), _locations)
def test_stored_drafts_never_throw_and_offer_only_usable_sessions(
    worker: Worker, data: st.DataObject, location: dict[str, str]
) -> None:
    saved = _mutated_state(worker, data)
    address = f"/o/r@{COMMIT}?root=.&document=#s={fragment(saved)}"
    record = data.draw(
        st.one_of(
            st.just({"version": 1, "address": address, "savedAt": 1}),
            mutations({"version": 1, "address": address, "savedAt": 1}).map(
                lambda m: m.apply({"version": 1, "address": address, "savedAt": 1})
            ),
        )
    )
    stored = data.draw(st.one_of(st.just(json.dumps(record)), st.text(max_size=20)))
    result = worker.value("draft", stored, location)
    if result["offered"] is not None:
        assert result["offered"] == result["read"]
        assert result["shown"] is not None, "an offered draft must be resumable"


@given(st.data())
def test_valid_drafts_round_trip_through_storage(
    worker: Worker, data: st.DataObject
) -> None:
    state = captured_state(worker)
    state["curation"]["annotations"] = [
        {"path": "", "text": data.draw(st.text(max_size=20))}
    ]
    address = f"/o/r@{COMMIT}?root=.&document=#s={fragment(state)}"
    now = data.draw(st.integers(0, 2**52))
    result = worker.value("saveAndRead", address, now)
    assert result == {
        "saved": True,
        "read": {"version": 1, "address": address, "savedAt": now},
    }


@given(st.data())
def test_synthetic_responses_are_adopted_or_refused_in_a_controlled_way(
    worker: Worker, data: st.DataObject
) -> None:
    # Synthetic: forged service responses, not demonstrated reachable inputs.
    response = worker.value("example")
    candidate = data.draw(mutations(response)).apply(response)
    result = worker.call("preparePreview", candidate, ORIGIN)
    assert controlled(result), result["error"]
    if result["ok"]:
        assert result["value"]["address"].startswith(
            f"/{candidate['repository']['owner']}/{candidate['repository']['name']}@"
        )


_DEPTH = 100_000


@pytest.mark.parametrize(
    "text",
    [
        "[" * _DEPTH + "]" * _DEPTH,
        '{"a":' * _DEPTH + "0" + "}" * _DEPTH,
        "[" * _DEPTH,
        "A" * 4_000_000,
        json.dumps({"text": "x" * 3_000_000}),
    ],
    ids=["deep-arrays", "deep-objects", "unclosed", "long-garbage", "long-state"],
)
def test_fragment_length_and_depth_boundaries(worker: Worker, text: str) -> None:
    # The service's request limit does not protect decoding before a request.
    encoded = base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")
    for candidate in (text, encoded):
        decoded = worker.value("decodeState", candidate)
        assert decoded is None or isinstance(decoded, dict)
        assert worker.value("startup", f"/o/r@{COMMIT}", "#s=" + candidate)["route"]
