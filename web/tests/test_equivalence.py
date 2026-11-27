"""Matching snapshots and curation produce identical local and hosted output."""

import pytest
from fastapi.testclient import TestClient

from treestamp.cli_inputs import read_source
from treestamp.document import Document, parse_document, render_region
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


@pytest.mark.parametrize("style", ["unicode", "ascii"])
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
    snapshot = capture_snapshot(repo.path / root)
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


@pytest.mark.parametrize("comment", ["# café".encode(), b"# legacy \x80"])
def test_loaded_documents_exchange_between_editors(
    client: TestClient, repo: Repo, comment: bytes
) -> None:
    settings = Settings(root="sub", attribution=True)
    local = TreeSession(capture_snapshot(repo.path / "sub").tree, settings)
    local.expand("deep")
    local.set_annotation("deep/leaf.txt", "local note")
    local.hide("other.txt")
    document = Document(local.printed_tree(), settings, frozenset({"sub/other.txt"}))
    region = (
        render_region(document)
        .encode()
        .replace(
            b"<!-- treestamp:config\n", b"<!-- treestamp:config\n" + comment + b"\n"
        )
    )
    path = repo.path / "README.md"
    path.write_bytes(b"\xef\xbb\xbf" + region.replace(b"\n", b"\r\n"))
    repo.commit()

    # Both loaders accept the same original bytes and prepare the same output.
    editor = read_source(str(path)).editor()
    response = client.post("/api/preview", json={"url": "o/r", "document": "README.md"})
    assert response.status_code == 200, response.text
    assert response.json()["region"] == editor.region_text()
    assert parse_document(editor.region_text().encode()) == document

    # Publish local output, load it through the hosted path, and make an edit.
    editor.write("README.md")
    repo.commit()
    response = client.post("/api/preview", json={"url": "o/r", "document": "README.md"})
    assert response.status_code == 200, response.text
    body = post_op(client, response.json(), "annotate", "deep/leaf.txt", "web note")

    # The hosted export remains loadable and editable through the local path.
    exported = body["region"].encode()
    path.write_bytes(exported)
    repo.commit()
    restored = read_source(str(path)).editor()
    assert restored.document() == parse_document(exported)
    assert restored.region_text().encode() == exported
    with restored.edit():
        restored.state.session.set_annotation("deep/leaf.txt", "local follow-up")
    assert "local follow-up" in restored.region_text()
