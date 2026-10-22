import pytest

from treestamp_web.github import GitHubClient, NotFoundError
from treestamp_web.preview import PreviewError

from .conftest import Clock
from .test_preview import op, preview, service_for, stamp


def pinned(commit: str, **params: str) -> dict[str, str]:
    return {"url": "", "owner": "o", "repo": "r", "ref": commit, **params}


def test_private_metadata_denies_content_even_with_privileged_token(fake):
    fake.options.private = True
    service, client = service_for(fake, github_token="can-read-private")
    with pytest.raises(NotFoundError, match="not public"):
        preview(service)
    assert client.calls == 1
    assert service.stats()["trees"] == 0


def test_cold_sha_must_equal_public_default_head(fake, repo):
    old = repo.git("rev-parse", "HEAD").strip()
    repo.commit("new default head")
    service, client = service_for(fake)
    with pytest.raises(PreviewError) as failure:
        preview(service, **pinned(old))
    assert failure.value.code == "snapshot_unavailable"
    assert service.stats()["trees"] == 0
    assert client.calls == 3  # metadata and current branch commit; no old objects
    current = repo.git("rev-parse", "HEAD").strip()
    assert preview(service, **pinned(current)).commit == current


def test_default_branch_changes_preserve_old_snapshot(fake, repo):
    service, client = service_for(fake)
    first = preview(service)
    repo.git("checkout", "-b", "release/stable")
    repo.write("new-default.txt")
    repo.commit()
    second = preview(service)
    assert second.commit != first.commit and second.default_branch == "release/stable"
    calls = client.calls
    assert "new-default.txt" not in op(service, first, "restore").tree
    assert client.calls == calls


def test_cached_snapshot_works_offline_and_after_private(fake, repo, monkeypatch):
    stamp(repo)
    service, client = service_for(fake)
    first = preview(service)
    fake.options.private = True
    with pytest.raises(NotFoundError, match="not public"):
        preview(service)

    async def offline(*args, **kwargs):
        raise AssertionError("cached snapshot must not contact GitHub")

    monkeypatch.setattr(GitHubClient, "_get", offline)
    calls = client.calls
    assert op(service, first, "annotate", "", "offline").dirty
    assert preview(service, **pinned(first.commit)).region == first.region
    assert client.calls == calls


def test_force_pushed_default_head_is_acquired_without_rebinding_old_draft(fake, repo):
    service, client = service_for(fake)
    first = preview(service)
    ancestor = repo.git("rev-parse", "HEAD~1").strip()
    repo.git("reset", "--hard", ancestor)
    replacement = preview(service)
    assert replacement.commit == ancestor and replacement.commit != first.commit
    calls = client.calls
    assert op(service, first, "restore").region == first.region
    assert client.calls == calls


def test_edits_cached_url_and_replacement_never_renew_old_deadline(fake, repo):
    clock = Clock()
    service, client = service_for(fake, clock)
    first = preview(service)
    clock.now += 2400
    op(service, first, "annotate", "", "note")
    repo.commit("replacement head")
    clock.now += 600
    second = preview(service)
    assert second.commit != first.commit
    assert preview(service, **pinned(first.commit)).commit == first.commit
    clock.now += 600
    calls = client.calls
    with pytest.raises(PreviewError, match="snapshot is unavailable"):
        op(service, first, "restore")
    assert client.calls == calls
    assert op(service, second, "restore").commit == second.commit


def test_successful_fresh_url_load_renews_same_current_snapshot(fake):
    clock = Clock()
    service, _ = service_for(fake, clock)
    first = preview(service)
    clock.now += 3500
    confirmed = preview(service)
    assert confirmed.commit == first.commit
    clock.now += 200
    assert op(service, first, "restore").commit == first.commit
    clock.now += 3400
    with pytest.raises(PreviewError, match="snapshot is unavailable"):
        op(service, first, "restore")


def test_failed_url_load_neither_admits_nor_renews_snapshot(fake):
    clock = Clock()
    service, _ = service_for(fake, clock)
    with pytest.raises(PreviewError):
        preview(service, document="missing.md")
    assert service.stats()["trees"] == 0
    first = preview(service)
    clock.now += 3500
    with pytest.raises(PreviewError):
        preview(service, document="missing.md")
    clock.now += 100
    with pytest.raises(PreviewError, match="snapshot is unavailable"):
        op(service, first, "restore")


def test_expired_historical_sha_is_not_refetched(fake, repo):
    clock = Clock()
    service, client = service_for(fake, clock)
    first = preview(service)
    repo.commit("advance")
    clock.now += 3600
    calls = client.calls
    with pytest.raises(PreviewError, match="snapshot is unavailable"):
        preview(service, **pinned(first.commit))
    assert client.calls - calls == 3  # only current metadata/HEAD proof
    assert service.stats()["trees"] == 0


@pytest.mark.parametrize("missing", ["document", "symlinks"])
def test_cached_snapshot_never_backfills_missing_historical_objects(
    fake, repo, missing
):
    stamp(repo)
    service, client = service_for(fake)
    first = preview(service, root="sub", document="")
    repo.commit("advance")
    calls = client.calls
    params = (
        {"root": "sub", "document": "README.md"}
        if missing == "document"
        else {"root": ".", "document": ""}
    )
    with pytest.raises(PreviewError, match="snapshot is unavailable"):
        preview(service, **pinned(first.commit, **params))
    assert client.calls == calls
    assert op(service, first, "restore").commit == first.commit


def test_eviction_and_restart_remove_historical_authorization(fake, repo):
    service, client = service_for(fake, cache_max_trees=1)
    first = preview(service)
    repo.commit("advance")
    second = preview(service)
    calls = client.calls
    with pytest.raises(PreviewError, match="snapshot is unavailable"):
        op(service, first, "restore")
    assert client.calls == calls
    restarted, restarted_client = service_for(fake)
    with pytest.raises(PreviewError, match="snapshot is unavailable"):
        op(restarted, second, "restore")
    assert restarted_client.calls == 0


def test_reused_name_does_not_reuse_other_repository_identity(fake, repo):
    service, _ = service_for(fake)
    first = preview(service)
    fake.options.repository_id = 2
    repo.commit("new repository identity")
    second = preview(service)
    with pytest.raises(PreviewError, match="snapshot is unavailable"):
        op(service, first, "restore")
    assert op(service, second, "restore").commit == second.commit


def test_unsupported_hidden_descendant_is_rejected_on_load(fake, repo):
    stamp(repo, hidden=("sub",))
    repo.write("sub/odd -> name")
    repo.commit("unsupported descendant")
    service, _ = service_for(fake)
    with pytest.raises(PreviewError, match="cannot load safely"):
        preview(service)
    assert service.stats()["trees"] == 0
    assert preview(service, root="sub/deep", document="").root == "sub/deep"


def test_failed_candidate_edit_preserves_previously_accepted_document(fake, repo):
    repo.write("x")
    repo.write("x  # y")
    repo.commit("annotation collision fixture")
    service, _ = service_for(fake)
    first = preview(service, document="")
    with pytest.raises(PreviewError, match="cannot represent"):
        op(service, first, "annotate", "x", "y")
    restored = op(service, first, "restore")
    assert restored.state == first.state and restored.region == first.region
