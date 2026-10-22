"""Matching snapshots and curation produce identical local and hosted output."""

import pytest
from fastapi.testclient import TestClient

from treestamp.document import Document, render_region
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings, repo_path
from treestamp.session import TreeSession

from .conftest import Repo


def post_op(
    client: TestClient, body: dict, kind: str, path: str = "", text: str = ""
) -> dict:
    response = client.post(
        "/api/op",
        json={
            "owner": body["repository"]["owner"],
            "repo": body["repository"]["name"],
            "ref": body["ref"]["commit"],
            "root": body["root"],
            "document": body["document"],
            "state": body["state"],
            "op": {"type": kind, "path": path, "text": text},
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
@pytest.mark.parametrize("counts", [True, False])
@pytest.mark.parametrize("root", [".", "sub"])
def test_equivalent_session_operations(
    client: TestClient, repo: Repo, style: str, counts: bool, root: str
) -> None:
    response = client.get(
        "/api/preview", params={"url": "o/r", "root": root, "document": ""}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    settings = Settings(root=root, style=style, show_counts=counts)
    snapshot = capture_snapshot(repo.path / root, "HEAD")
    local = TreeSession(snapshot.tree, settings)
    body["state"]["curation"]["settings"].update(style=style, show_counts=counts)
    body = post_op(client, body, "restore")
    assert body["region"] == render_region(Document(local.printed_tree(), settings))
    directory = "sub" if root == "." else "deep"
    local.expand(directory)
    body = post_op(client, body, "expand", directory)
    local.set_annotation(directory, "directory annotation")
    body = post_op(client, body, "annotate", directory, "directory annotation")
    file = "top.txt" if root == "." else "other.txt"
    local.hide(file)
    body = post_op(client, body, "hide", file)
    hidden = frozenset(repo_path(path, root) for path in local.saved_hidden())
    assert body["region"] == render_region(
        Document(local.printed_tree(), settings, hidden)
    )
    assert body["state"]["curation"] == local.state().to_dict()
