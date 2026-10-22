from dataclasses import replace

import pytest

from treestamp.sources import TreeRecord
from treestamp_web.cache import Snapshot, SnapshotCache
from treestamp_web.github import Resolved, TooLargeError
from treestamp_web.links import Repository

from .conftest import Clock, make_config


def snapshot(commit: str, *, count: int = 1, blob: bytes = b"target") -> Snapshot:
    return Snapshot(
        1,
        Resolved(commit, "tree"),
        [TreeRecord(str(index), "100644", "blob", "blob") for index in range(count)],
        "main",
        {"blob": blob},
    )


def test_snapshots_expire_without_reads_renewing_them() -> None:
    clock = Clock()
    cache = SnapshotCache(make_config(), clock)
    repo = Repository("o", "r", "a")
    first = snapshot("a")
    cache.put(repo, first)
    clock.now += 3599
    assert cache.get(repo) is first
    clock.now += 1
    assert cache.get(repo) is None
    assert cache.stats() == {"trees": 0, "tree_rows": 0, "blobs": 0, "refs": 0}


@pytest.mark.parametrize(
    "limits",
    [
        {"cache_max_trees": 1},
        {"cache_max_entries": 1},
        {"cache_max_blobs": 1},
        {"cache_max_blob_bytes": 6},
    ],
)
def test_pressure_evicts_content_and_provenance_together(limits):
    cache = SnapshotCache(make_config(**limits), Clock())
    repo = Repository("o", "r")
    cache.put(repo, snapshot("a"))
    cache.put(repo, snapshot("b"))
    assert cache.get(repo.at("a")) is None
    assert cache.get(repo.at("b")).blobs == {"blob": b"target"}
    assert cache.stats() == {"trees": 1, "tree_rows": 1, "blobs": 1, "refs": 1}


def test_oversized_candidate_does_not_evict_accepted_snapshot() -> None:
    cache = SnapshotCache(make_config(cache_max_entries=1), Clock())
    repo = Repository("o", "r")
    first = snapshot("a")
    cache.put(repo, first)
    with pytest.raises(TooLargeError, match="retention limits"):
        cache.put(repo, snapshot("b", count=2))
    assert cache.get(repo.at("a")) is first


def test_identity_change_discards_only_same_repository_name() -> None:
    cache = SnapshotCache(make_config(), Clock())
    repo = Repository("O", "R")
    cache.put(repo, snapshot("a"))
    cache.put(Repository("o", "other"), snapshot("a"))
    cache.discard_other_identities(repo, 2)
    assert cache.get(repo.at("a")) is None
    assert cache.get(Repository("o", "other", "a")) is not None
    current = replace(snapshot("a"), identity=2)
    cache.put(repo, current)
    cache.discard_other_identities(repo, 2)
    assert cache.get(Repository("o", "r", "a")) is current
    cache.close()
    assert cache.stats()["trees"] == 0


def test_overlapping_loads_preserve_all_previously_accepted_facts() -> None:
    clock = Clock()
    cache = SnapshotCache(make_config(), clock)
    repo = Repository("o", "r", "a")
    first = snapshot("a")
    cache.put(repo, first)
    clock.now += 3000
    cache.put(repo, replace(first, blobs={"other": b"other target"}))
    assert cache.get(repo).blobs == {"blob": b"target", "other": b"other target"}
    clock.now += 601
    assert cache.get(repo) is not None


def test_combined_facts_exceeding_limits_do_not_replace_accepted_snapshot() -> None:
    cache = SnapshotCache(make_config(cache_max_blobs=1), Clock())
    repo = Repository("o", "r", "a")
    first = snapshot("a")
    cache.put(repo, first)
    with pytest.raises(TooLargeError):
        cache.put(repo, replace(first, blobs={"other": b"other target"}))
    assert cache.get(repo).blobs == first.blobs
