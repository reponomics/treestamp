"""Atomic, temporary retention of snapshots acquired as public default HEADs."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from treestamp_web.github import TooLargeError

if TYPE_CHECKING:
    from collections.abc import Callable

    from treestamp.sources import TreeRecord
    from treestamp_web.config import Config
    from treestamp_web.github import Resolved
    from treestamp_web.links import Repository

SNAPSHOT_SECONDS = 3600
SnapshotKey = tuple[str, str, str]


@dataclass(frozen=True)
class Snapshot:
    identity: int
    resolved: Resolved
    records: list[TreeRecord]
    default_branch: str | None
    blobs: dict[str, bytes]


@dataclass
class _Retained:
    snapshot: Snapshot
    expires: float
    timer: asyncio.TimerHandle | None = None


def _key(repo: Repository, commit: str) -> SnapshotKey:
    return repo.owner.lower(), repo.name.lower(), commit


class SnapshotCache:
    """Evict records, blobs, and provenance together; reads never extend expiry."""

    def __init__(self, config: Config, clock: Callable[[], float]) -> None:
        self._config, self._clock = config, clock
        self._items: OrderedDict[SnapshotKey, _Retained] = OrderedDict()

    def _remove(self, key: SnapshotKey) -> None:
        entry = self._items.pop(key)
        if entry.timer is not None:
            entry.timer.cancel()

    def close(self) -> None:
        for key in list(self._items):
            self._remove(key)

    def _prune(self) -> None:
        now = self._clock()
        for key, entry in list(self._items.items()):
            if now >= entry.expires:
                self._remove(key)

    def get(self, repo: Repository) -> Snapshot | None:
        self._prune()
        key = _key(repo, repo.ref)
        entry = self._items.get(key)
        if entry is None:
            return None
        self._items.move_to_end(key)
        return entry.snapshot

    def discard_other_identities(self, repo: Repository, identity: int) -> None:
        """A reused owner/name must not combine snapshots from different repos."""
        prefix = _key(repo, "")[:2]
        for key, entry in list(self._items.items()):
            if key[:2] == prefix and entry.snapshot.identity != identity:
                self._remove(key)

    @staticmethod
    def _cost(snapshot: Snapshot) -> tuple[int, int, int, int]:
        return (
            1,
            len(snapshot.records),
            len(snapshot.blobs),
            sum(map(len, snapshot.blobs.values())),
        )

    def _fits(self, cost: tuple[int, int, int, int]) -> bool:
        limits = (
            self._config.cache_max_trees,
            self._config.cache_max_entries,
            self._config.cache_max_blobs,
            self._config.cache_max_blob_bytes,
        )
        return all(value <= limit for value, limit in zip(cost, limits, strict=True))

    def _total_cost(self) -> tuple[int, int, int, int]:
        costs = [self._cost(entry.snapshot) for entry in self._items.values()]
        totals = [sum(cost[index] for cost in costs) for index in range(4)]
        return totals[0], totals[1], totals[2], totals[3]

    def put(self, repo: Repository, snapshot: Snapshot) -> None:
        """Publish only a successfully loaded candidate, renewing its deadline."""
        self._prune()
        key = _key(repo, snapshot.resolved.commit)
        previous = self._items.get(key)
        if previous is not None and previous.snapshot.identity == snapshot.identity:
            # Concurrent URL loads may acquire facts for different subtrees or
            # documents. A later completion must retain both accepted sessions.
            snapshot = replace(
                snapshot, blobs={**previous.snapshot.blobs, **snapshot.blobs}
            )
        if not self._fits(self._cost(snapshot)):
            raise TooLargeError("the snapshot exceeds the service's retention limits")
        if key in self._items:
            self._remove(key)
        entry = _Retained(snapshot, self._clock() + SNAPSHOT_SECONDS)
        self._items[key] = entry
        # Remove expired content even if no later request arrives. Fake-clock
        # tests and callers without a running event loop also prune on access.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            entry.timer = loop.call_later(SNAPSHOT_SECONDS, self._prune)
        while not self._fits(self._total_cost()):
            self._remove(next(iter(self._items)))

    def stats(self) -> dict[str, int]:
        self._prune()
        trees, rows, blobs, _ = self._total_cost()
        return {"trees": trees, "tree_rows": rows, "blobs": blobs, "refs": trees}
