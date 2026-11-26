"""One off-loop SVG job at a time, with a shared measured-work budget."""

from __future__ import annotations

import asyncio
import math
import time
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Lock
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable

_T = TypeVar("_T")
# A short burst accommodates an edit followed by export. Sustained work gets
# one render-second per four wall seconds, shared by all clients and routes.
WORK_CAPACITY = 2.0
WORK_REFILL = 0.25


class SvgBusyError(Exception):
    def __init__(self, retry_after: int = 1) -> None:
        super().__init__("SVG generation is busy; try again shortly")
        self.retry_after = retry_after


class SvgWorkPool:
    """Reject excess work; cancellation never frees a still-running worker."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="svg")
        self._lock = Lock()
        self._active = False
        self._closed = False
        self._credit = WORK_CAPACITY
        self._last = clock()

    def _refill(self, now: float) -> None:
        self._credit = min(
            WORK_CAPACITY, self._credit + max(0, now - self._last) * WORK_REFILL
        )
        self._last = now

    def _submit(self, work: Callable[[], _T]) -> Future[_T]:
        with self._lock:
            now = self._clock()
            self._refill(now)
            if self._closed or self._active:
                raise SvgBusyError()
            if self._credit <= 0:
                raise SvgBusyError(max(1, math.floor(-self._credit / WORK_REFILL) + 1))
            self._active = True
            try:
                future = self._executor.submit(work)
            except BaseException:
                self._active = False
                raise
        # A concurrent future callback runs even if its async caller disconnects
        # or its event loop closes. Only actual completion releases the slot.
        future.add_done_callback(lambda _: self._finished(now))
        return future

    def _finished(self, started: float) -> None:
        with self._lock:
            now = self._clock()
            self._refill(now)
            self._credit -= max(0, now - started)
            self._active = False

    async def run(self, work: Callable[[], _T]) -> _T:
        future = asyncio.wrap_future(self._submit(work))
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # Retrieve a later failure even when the original caller is gone.
            future.add_done_callback(lambda done: done.exception())
            raise

    def close(self) -> None:
        """Stop admission; a currently running bounded job finishes normally."""
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=False)

    async def aclose(self) -> None:
        self.close()
        await asyncio.to_thread(self._executor.shutdown, wait=True)
