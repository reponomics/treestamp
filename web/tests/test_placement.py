"""Provisional placement replays through the shared core without editing browsing state."""

from __future__ import annotations

import asyncio
import base64
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from treestamp.document import Document, render_region
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings
from treestamp.session import TreeSession
from treestamp.sources import TreeRecord, tree_from_records
from treestamp_web.app import create_app
from treestamp_web.cache import SNAPSHOT_SECONDS
from treestamp_web.localgit import FakeGitHub, LocalRepository
from treestamp_web.placement import MAX_DECISIONS, parse_placement_request
from treestamp_web.preview import PreviewError
from treestamp_web.routing import COOKIE

from .conftest import Clock, Repo, make_config, transport_for
from .test_preview import op, preview, service_for


def stale(repo: Repo) -> FakeGitHub:
    for path in ("old/nested/a.py", "old/nested/b.py", "old/gone.py", "README.md"):
        repo.write(path)
    repo.git("add", ".")
    session = TreeSession(capture_snapshot(repo.path).tree, Settings())
    for path in ("old", "old/nested"):
        session.expand(path)
    session.set_annotation("old/nested/a.py", "First note")
    session.set_annotation("old/nested/b.py", "Second note")
    session.set_annotation("old/gone.py", "Removed note")
    repo.write("README.md", render_region(Document(session.printed_tree(), Settings())))
    repo.commit("annotated source")
    repo.git("mv", "old", "new")
    (repo.path / "new/gone.py").unlink()
    repo.commit("moved directory")
    return FakeGitHub(LocalRepository(repo.path))


def body(opened, decisions=None, **extra):
    return {
        "owner": "o",
        "repo": "r",
        "ref": opened.commit,
        "root": opened.root,
        "document": opened.document,
        "state": opened.state,
        "decisions": [] if decisions is None else decisions,
        **extra,
    }


def placed(service, opened, decisions=None, **extra):
    return asyncio.run(
        service.place(parse_placement_request(body(opened, decisions, **extra)))
    )


def test_fresh_load_offers_notes_but_restore_does_not(repo: Repo) -> None:
    service, client = service_for(stale(repo))
    opened = preview(service)
    metadata = opened.to_dict(None)["placement"]
    assert metadata["total"] == metadata["remaining"] == 3
    assert metadata["current"]["path"] == "old"
    assert metadata["current"]["annotation"] == ""
    assert metadata["current"]["kind"] == "dir"
    assert not metadata["can_undo"]
    calls = client.calls
    restored = op(service, opened, "restore")
    assert "placement" not in restored.to_dict(None)
    assert client.calls == calls


def test_recursive_directory_transfer_retains_missing_path_and_undo_replays(
    repo: Repo,
) -> None:
    service, client = service_for(stale(repo))
    opened = preview(service)
    calls = client.calls
    result = placed(service, opened, [{"type": "place", "path": "new"}])
    assert result.placement["remaining"] == 1
    assert result.placement["placed_count"] == 2
    assert result.placement["current"]["path"] == "old/gone.py"
    assert "First note" in result.region and "Second note" in result.region
    assert "Removed note" not in result.region
    assert result.state["curation"]["expanded"] == ["new", "new/nested"]
    assert result.state["revision"] == 1
    assert result.placement["can_undo"]
    undone = placed(service, opened, [])
    assert undone.region == opened.region
    assert undone.state == opened.state
    assert undone.placement["current"]["path"] == "old"
    completed = placed(
        service, opened, [{"type": "place", "path": "new"}, {"type": "skip"}]
    )
    assert completed.placement["current"] is None
    assert completed.placement["unplaced"] == 1
    assert completed.placement["can_undo"]
    assert client.calls == calls


def test_browsing_expansion_changes_only_placement_rows(repo: Repo) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    result = placed(service, opened, expanded=["new", "new/nested"], reveal=True)
    assert result.region == opened.region
    assert result.state == opened.state
    assert result.rows == opened.rows
    assert "new/nested/a.py" in {row["path"] for row in result.placement["rows"]}
    assert "new/nested/a.py" not in {row["path"] for row in result.rows}
    with pytest.raises(PreviewError) as error:
        placed(service, opened, expanded=["new/nested/a.py"])
    assert error.value.status == 400


def test_replacement_requires_confirmation_and_original_state_is_unchanged(
    repo: Repo,
) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    # Original envelopes support existing destination annotations.
    opened.state["curation"]["annotations"].append(
        {"path": "new/nested/a.py", "text": "Existing"}
    )
    original = deepcopy(opened.state)
    decisions = [
        {"type": "skip"},
        {"type": "place", "path": "new/nested/a.py"},
    ]
    with pytest.raises(PreviewError) as error:
        placed(service, opened, decisions)
    assert error.value.status == 409
    assert error.value.code == "placement_conflict"
    assert error.value.extra["question"] == str(error.value)
    assert opened.state == original
    decisions[-1]["replace"] = True
    result = placed(service, opened, decisions)
    assert "First note" in result.region
    undone = placed(service, opened, decisions[:-1])
    notes = undone.state["curation"]["annotations"]
    assert {"path": "new/nested/a.py", "text": "Existing"} in notes


def test_kind_mismatch_and_decisions_after_completion_are_rejected(repo: Repo) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    with pytest.raises(PreviewError) as error:
        placed(service, opened, [{"type": "place", "path": "new/nested/a.py"}])
    assert error.value.status == 400
    with pytest.raises(PreviewError):
        placed(service, opened, [{"type": "skip"}] * 5)


@pytest.mark.parametrize(
    "change",
    [
        {"decisions": None},
        {"decisions": [{}]},
        {"decisions": [{"type": "skip", "path": "new"}]},
        {"decisions": [{"type": "place"}]},
        {"decisions": [{"type": "place", "path": "new", "replace": 1}]},
        {"decisions": [{"type": "annotate"}]},
        {"decisions": [False]},
        {"decisions": [{"type": "skip"}] * (MAX_DECISIONS + 1)},
        {"expanded": "new"},
        {"expanded": None},
        {"expanded": ["new", "new"]},
        {"expanded": [False]},
        {"reveal": "true"},
        {"extra": True},
        {"ref": "main"},
        {"root": "different"},
    ],
)
def test_invalid_request_fields(repo: Repo, change: dict) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    with pytest.raises(PreviewError):
        parse_placement_request(body(opened) | change)


def test_only_original_loaded_envelope_can_start_placement(repo: Repo) -> None:
    service, _ = service_for(stale(repo))
    new = preview(service, document="")
    with pytest.raises(PreviewError):
        parse_placement_request(body(new))
    opened = preview(service)
    result = placed(service, opened, [{"type": "skip"}])
    with pytest.raises(PreviewError):
        parse_placement_request(body(result))


def test_expired_snapshot_never_fetches_and_decisions_renew_lease(repo: Repo) -> None:
    clock = Clock()
    service, client = service_for(stale(repo), clock)
    opened = preview(service)
    calls = client.calls
    clock.now += SNAPSHOT_SECONDS - 10
    placed(service, opened, [{"type": "skip"}])
    clock.now += SNAPSHOT_SECONDS - 10
    placed(service, opened, [])
    clock.now += 11
    with pytest.raises(PreviewError) as error:
        placed(service, opened, [])
    assert error.value.status == 410
    assert client.calls == calls


def test_endpoint_rate_limit_body_limit_and_affinity(repo: Repo) -> None:
    fake = stale(repo)
    app = create_app(
        make_config(op_rate_limit_per_minute=1), transport=transport_for(fake)
    )
    with TestClient(app) as client:
        opened = client.get("/api/preview", params={"url": "o/r"}).json()
        request = {
            "owner": "o",
            "repo": "r",
            "ref": opened["ref"]["commit"],
            "state": opened["state"],
            "decisions": [],
        }
        assert client.post("/api/placement", json=request).status_code == 200
        assert client.post("/api/placement", json=request).status_code == 429
    limited = create_app(
        make_config(max_state_bytes=100), transport=transport_for(fake)
    )
    with TestClient(limited) as client:
        assert client.post("/api/placement", content=b"x" * 101).status_code == 413
    routed = create_app(
        make_config(fly_session_routing=True, fly_machine_id="a" * 14),
        transport=transport_for(fake),
    )
    with TestClient(routed, follow_redirects=False) as client:
        result = client.post(
            "/api/placement", json={}, headers={"cookie": f"{COOKIE}={'b' * 14}"}
        )
        assert result.status_code == 307
        assert "instance=" + "b" * 14 in result.headers["fly-replay"]


def test_collision_requeues_displaced_note_and_undo_restores_mapping(
    repo: Repo,
) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    first = [{"type": "skip"}, {"type": "place", "path": "new/nested/a.py"}]
    second = {"type": "place", "path": "new/nested/a.py", "replace": True}
    result = placed(service, opened, [*first, second])
    assert result.placement["placed_count"] == 1
    assert result.placement["remaining"] == 2
    assert {"path": "new/nested/a.py", "text": "Second note"} in result.state[
        "curation"
    ]["annotations"]
    undone = placed(service, opened, first)
    assert undone.placement["current"]["path"] == "old/nested/b.py"
    assert {"path": "new/nested/a.py", "text": "First note"} in undone.state[
        "curation"
    ]["annotations"]
    returned = placed(service, opened, [*first, second, {"type": "skip"}])
    assert returned.placement["current"]["path"] == "old/nested/a.py"


def test_directory_leaves_conflicting_descendant_in_queue(repo: Repo) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    opened.state["curation"]["annotations"].append(
        {"path": "new/nested/a.py", "text": "Existing"}
    )
    result = placed(service, opened, [{"type": "place", "path": "new"}])
    assert result.placement["placed_count"] == 1
    assert result.placement["remaining"] == 2
    assert result.placement["current"]["path"] == "old/nested/a.py"
    assert {"path": "new/nested/a.py", "text": "Existing"} in result.state["curation"][
        "annotations"
    ]
    assert {"path": "new/nested/b.py", "text": "Second note"} in result.state[
        "curation"
    ]["annotations"]


def test_raw_byte_paths_retain_identity_in_source_destination_and_undo(
    repo: Repo,
) -> None:
    source = "before\udcff"
    destination = b"after\xfe"
    tree = tree_from_records([TreeRecord(source, "100644", "blob", "a" * 40)])
    session = TreeSession(tree, Settings())
    session.set_annotation(source, "Raw note")
    repo.write("README.md", render_region(Document(session.printed_tree(), Settings())))
    repo.commit("original document")
    oid = repo.git("hash-object", "-w", "--stdin", input_bytes=b"raw").strip()
    repo.git(
        "update-index",
        "-z",
        "--index-info",
        input_bytes=b"100644 " + oid.encode() + b"\t" + destination + b"\0",
    )
    repo.commit("new byte path", stage=False)
    service, _ = service_for(FakeGitHub(LocalRepository(repo.path)))
    opened = preview(service)
    current = opened.placement["current"]
    assert current["path"] == {"git_bytes": b"before\xff".hex()}
    assert current["key"] == b"before\xff".hex()
    path = {"git_bytes": destination.hex()}
    result = placed(service, opened, [{"type": "place", "path": path}])
    assert result.placement["current"] is None
    assert {"path": path, "text": "Raw note"} in result.state["curation"]["annotations"]
    assert placed(service, opened).state == opened.state


def test_baseline_without_region_is_bad_request_not_server_error(repo: Repo) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    opened.state["baseline"] = base64.b64encode(b"No region here").decode()
    with pytest.raises(PreviewError, match="invalid document baseline") as error:
        placed(service, opened)
    assert error.value.status == 400
