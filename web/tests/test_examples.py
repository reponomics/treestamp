"""Bundled examples remain complete, editable responses from the current API.

Server data records every path at each pinned public commit, including hidden
and collapsed paths needed for counts. Updating snapshots requires updating
both example.js and these inputs; this test never contacts GitHub.
"""

import json
from collections.abc import Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from treestamp_web.app import STATIC, create_app
from treestamp_web.examples import bundled_tree
from treestamp_web.links import Repository

from .conftest import Clock, make_config

EXAMPLES = json.loads(
    (STATIC / "example.js")
    .read_text(encoding="utf-8")
    .split("export const EXAMPLES = ", 1)[1]
    .strip()
    .removesuffix(";")
)
TREES = json.loads(
    (STATIC.parent / "data" / "examples.json").read_text(encoding="utf-8")
)


@pytest.fixture
def offline_client(clock: Clock) -> Iterator[TestClient]:
    def github(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/rate_limit", (
            f"unexpected GitHub request: {request.url}"
        )
        return httpx.Response(503)

    app = create_app(make_config(), transport=httpx.MockTransport(github), clock=clock)
    with TestClient(app) as client:
        yield client


def operation_body(name: str) -> dict[str, object]:
    example = EXAMPLES[name]
    return {
        "owner": example["repository"]["owner"],
        "repo": name,
        "ref": example["ref"]["commit"],
        "root": example["root"],
        "document": example["document"],
        "state": example["state"],
        "op": {"type": "restore"},
    }


@pytest.mark.parametrize("name", EXAMPLES)
def test_bundled_example_matches_current_api(
    offline_client: TestClient, name: str
) -> None:
    assert EXAMPLES.keys() == TREES.keys(), "refresh the bundled source trees too"
    response = offline_client.post("/api/op", json=operation_body(name))
    assert response.status_code == 200, response.text
    assert response.json() == EXAMPLES[name], (
        "regenerate bundled examples against the current API"
    )


@pytest.mark.parametrize("name", EXAMPLES)
def test_bundled_example_can_fold_expand_and_annotate_offline(
    offline_client: TestClient, name: str, clock: Clock
) -> None:
    example = EXAMPLES[name]
    directory = next(
        row["path"]
        for row in example["rows"]
        if row["path"] and row["kind"] == "dir" and not row["collapsed"]
    )
    body = operation_body(name)
    body["op"] = {"type": "toggle", "path": directory}
    folded = offline_client.post("/api/op", json=body)
    assert folded.status_code == 200, folded.text
    assert len(folded.json()["rows"]) < len(example["rows"])

    clock.now += 86_400  # Bundled trees outlive ordinary reference/cache expiry.
    body["state"] = folded.json()["state"]
    expanded = offline_client.post("/api/op", json=body)
    assert expanded.status_code == 200, expanded.text
    assert expanded.json()["region"] == example["region"]
    assert expanded.json()["state"]["curation"] == example["state"]["curation"]

    body["state"] = expanded.json()["state"]
    body["op"] = {"type": "annotate", "path": directory, "text": "My example note"}
    annotated = offline_client.post("/api/op", json=body)
    assert annotated.status_code == 200, annotated.text
    assert {"path": directory, "text": "My example note"} in annotated.json()["state"][
        "curation"
    ]["annotations"]
    assert "# My example note" in annotated.json()["tree"]


@pytest.mark.parametrize(
    "repo",
    [
        Repository(
            "someone-else",
            "reponomics-dashboard",
            TREES["reponomics-dashboard"]["commit"],
        ),
        Repository("reponomics", "other-repo", TREES["reponomics-dashboard"]["commit"]),
        Repository("reponomics", "reponomics-dashboard", "0" * 40),
        Repository("reponomics", "reponomics-dashboard", "HEAD"),
    ],
)
def test_other_repositories_and_refs_are_not_bundled(repo: Repository) -> None:
    assert bundled_tree(repo) is None


def test_fixture_does_not_authorize_fetching_missing_document(offline_client):
    example = EXAMPLES["reponomics-dashboard"]
    response = offline_client.get(
        "/api/preview",
        params={
            "owner": "reponomics",
            "repo": "reponomics-dashboard",
            "ref": example["ref"]["commit"],
            "document": "README.md",
        },
    )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "snapshot_unavailable"
