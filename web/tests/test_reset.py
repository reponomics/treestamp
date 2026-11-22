"""Discarding edits restores the accepted post-placement session start."""

from __future__ import annotations

from copy import deepcopy

import pytest

from treestamp_web.cache import SNAPSHOT_SECONDS
from treestamp_web.preview import Envelope, PreviewError

from .conftest import Clock, Repo
from .test_placement import placed, stale
from .test_preview import op, preview, service_for


def transferred(service):
    opened = preview(service)
    accepted = placed(
        service, opened, [{"type": "place", "path": "new"}, {"type": "skip"}]
    )
    return opened, accepted


def test_reset_restores_transfers_and_skips_without_reloading_source(
    repo: Repo,
) -> None:
    service, client = service_for(stale(repo))
    opened, accepted = transferred(service)
    initial = deepcopy(accepted.state["curation"])
    assert accepted.state["initial_curation"] == initial
    assert accepted.state["baseline"] == opened.state["baseline"]
    calls = client.calls
    edited = op(service, accepted, "annotate", "new/nested/a.py", "Later edit")
    edited = op(service, edited, "hide", "new/nested/b.py")
    edited = op(service, edited, "collapse", "new")
    edited.state["curation"]["settings"]["style"] = "ascii"
    edited.state["curation"]["settings"]["show_counts"] = False
    edited = op(service, edited, "present")
    before = deepcopy(edited.state)
    restored = op(service, edited, "reset")
    assert restored.state["curation"] == initial
    assert restored.state["initial_curation"] == initial
    assert restored.state["baseline"] == opened.state["baseline"]
    assert restored.state["generation"] == accepted.state["generation"]
    assert restored.state["revision"] == edited.state["revision"] + 1
    assert restored.region == accepted.region
    assert "First note" in restored.region and "Second note" in restored.region
    assert "Removed note" not in restored.region and "Later edit" not in restored.region
    assert "placement" not in restored.to_dict(None)
    assert edited.state == before
    assert client.calls == calls


def test_saved_session_restore_retains_post_transfer_reset_point(repo: Repo) -> None:
    service, _ = service_for(stale(repo))
    _, accepted = transferred(service)
    edited = op(service, accepted, "annotate", "new/nested/a.py", "Returned draft")
    serialized = deepcopy(edited.state)
    assert Envelope.from_dict(serialized).to_dict() == serialized
    resumed = op(service, edited, "restore")
    assert resumed.state == serialized
    assert "Returned draft" in resumed.region
    assert "placement" not in resumed.to_dict(None)
    reset = op(service, resumed, "reset")
    assert reset.region == accepted.region
    assert reset.state["initial_curation"] == accepted.state["curation"]


def test_reset_after_declining_transfer_keeps_removed_notes_omitted(repo: Repo) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    edited = op(service, opened, "annotate", "new", "New folder note")
    reset = op(service, edited, "reset")
    assert reset.region == opened.region
    assert reset.state["curation"] == opened.state["curation"]
    assert "placement" not in reset.to_dict(None)
    assert "First note" not in reset.region


def test_fresh_folder_reset_restores_defaults(repo: Repo) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service, document="", root="new")
    assert opened.state["baseline"] is None
    edited = op(service, opened, "annotate", "", "Temporary root note")
    reset = op(service, edited, "reset")
    assert reset.region == opened.region
    assert reset.state["curation"] == opened.state["initial_curation"]
    assert reset.state["baseline"] is None


def test_legacy_envelope_establishes_restored_draft_as_session_start(
    repo: Repo,
) -> None:
    service, _ = service_for(stale(repo))
    _, accepted = transferred(service)
    accepted.state.pop("initial_curation")
    assert "initial_curation" not in Envelope.from_dict(accepted.state).to_dict()
    resumed = op(service, accepted, "restore")
    assert resumed.state["initial_curation"] == accepted.state["curation"]
    edited = op(service, resumed, "annotate", "new", "Later note")
    reset = op(service, edited, "reset")
    assert reset.region == accepted.region
    assert "placement" not in reset.to_dict(None)


def test_first_legacy_edit_keeps_pre_edit_reset_point(repo: Repo) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    opened.state.pop("initial_curation")
    edited = op(service, opened, "annotate", "new", "Later note")
    assert edited.state["initial_curation"] == opened.state["curation"]
    assert op(service, edited, "reset").region == opened.region


@pytest.mark.parametrize("initial", [None, [], "invalid", {"unknown": []}])
def test_malformed_initial_curation_is_rejected(repo: Repo, initial: object) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    opened.state["initial_curation"] = initial
    with pytest.raises(PreviewError) as error:
        op(service, opened, "restore")
    assert error.value.status == 400
    assert error.value.code == "invalid_state"


@pytest.mark.parametrize("operation", ["reset", "restore", "annotate"])
@pytest.mark.parametrize("invalid", ["root", "expanded", "annotation"])
def test_initial_curation_is_validated_against_source_and_tree(
    repo: Repo, operation: str, invalid: str
) -> None:
    service, _ = service_for(stale(repo))
    opened = preview(service)
    initial = opened.state["initial_curation"]
    if invalid == "root":
        initial["settings"]["root"] = "new"
    elif invalid == "expanded":
        initial["expanded"] = ["missing"]
    else:
        initial["annotations"] = [{"path": "missing", "text": "Invalid note"}]
    before = deepcopy(opened.state)
    with pytest.raises(PreviewError) as error:
        op(service, opened, operation, "new", "Later note")
    assert error.value.status == 400
    assert error.value.code == "invalid_state"
    assert opened.state == before


def test_reset_renews_snapshot_lease_without_acquisition(repo: Repo) -> None:
    clock = Clock()
    service, client = service_for(stale(repo), clock)
    _, accepted = transferred(service)
    calls = client.calls
    clock.now += SNAPSHOT_SECONDS - 1
    reset = op(service, accepted, "reset")
    clock.now += 2
    assert op(service, reset, "restore").region == accepted.region
    assert client.calls == calls


def test_expired_reset_retains_state_and_never_fetches_another_snapshot(
    repo: Repo,
) -> None:
    clock = Clock()
    service, client = service_for(stale(repo), clock)
    _, accepted = transferred(service)
    edited = op(service, accepted, "annotate", "new", "Keep this draft")
    before = deepcopy(edited.state)
    calls = client.calls
    clock.now += SNAPSHOT_SECONDS + 1
    with pytest.raises(PreviewError) as error:
        op(service, edited, "reset")
    assert error.value.status == 410
    assert edited.state == before
    assert client.calls == calls
