"""SVG admission bounds CPU work without blocking the HTTP event loop."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient

from treestamp_web.app import create_app
from treestamp_web.config import Config, ConfigError
from treestamp_web.svg_work import SvgBusyError, SvgWorkPool

from .conftest import Clock, Repo, make_config, transport_for
from .test_svg import export_body, svg_source


def test_work_budget_charges_failed_jobs_and_recovers() -> None:
    clock = Clock()
    pool = SvgWorkPool(clock)

    def expensive_failure() -> str:
        clock.now += 3
        raise ValueError("failed after doing work")

    async def exercise() -> None:
        with pytest.raises(ValueError, match="doing work"):
            await pool.run(expensive_failure)
        with pytest.raises(SvgBusyError) as busy:
            await pool.run(lambda: "must not run")
        clock.now += busy.value.retry_after
        assert await pool.run(lambda: "recovered") == "recovered"
        # Ordinary edit + export bursts fit without a cooldown on every job.
        for _ in range(5):
            assert await pool.run(lambda: "small") == "small"
        await pool.aclose()
        with pytest.raises(SvgBusyError):
            await pool.run(lambda: "closed")

    asyncio.run(exercise())


def test_cancel_keeps_worker_busy_and_charges_work() -> None:
    clock = Clock()
    pool = SvgWorkPool(clock)
    entered, release = Event(), Event()

    def blocked() -> str:
        entered.set()
        assert release.wait(5)
        clock.now += 3
        return "finished"

    async def exercise() -> None:
        pending = asyncio.create_task(pool.run(blocked))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
            with pytest.raises(SvgBusyError):
                await pool.run(lambda: "must not queue")
        finally:
            release.set()
            # Wait for actual completion, including the accounting callback.
            await asyncio.to_thread(pool._executor.shutdown, wait=True)
        with pytest.raises(SvgBusyError) as busy:
            await pool.run(lambda: "must not evade debt")
        assert busy.value.retry_after > 1
        await pool.aclose()

    asyncio.run(exercise())


def test_cancelled_failing_work_does_not_leave_async_exception() -> None:
    pool = SvgWorkPool()
    entered, release = Event(), Event()

    def blocked_failure() -> str:
        entered.set()
        assert release.wait(5)
        raise ValueError("late failure")

    async def exercise() -> None:
        errors: list[object] = []
        asyncio.get_running_loop().set_exception_handler(
            lambda loop, context: errors.append(context)
        )
        pending = asyncio.create_task(pool.run(blocked_failure))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            pending.cancel()
            with pytest.raises(asyncio.CancelledError):
                await pending
        finally:
            release.set()
            await pool.aclose()
        await asyncio.sleep(0)
        assert not errors

    asyncio.run(exercise())


def test_executor_submission_failure_releases_admission(monkeypatch) -> None:
    pool = SvgWorkPool()

    def fail(*args):
        raise RuntimeError("cannot start worker")

    with monkeypatch.context() as patch:
        patch.setattr(pool._executor, "submit", fail)
        with pytest.raises(RuntimeError, match="cannot start"):
            asyncio.run(pool.run(lambda: "unused"))
    assert asyncio.run(pool.run(lambda: "recovered")) == "recovered"
    pool.close()


def test_export_rate_configuration_is_separate() -> None:
    config = Config.from_env({"SVG_EXPORT_RATE_LIMIT_PER_MINUTE": "7"})
    assert config.svg_export_rate_limit_per_minute == 7
    assert config.op_rate_limit_per_minute == 240
    with pytest.raises(ConfigError, match="SVG_EXPORT_RATE_LIMIT_PER_MINUTE"):
        Config.from_env({"SVG_EXPORT_RATE_LIMIT_PER_MINUTE": "-1"})


def test_blocked_export_leaves_health_responsive_and_rejects_queue(
    client: TestClient, monkeypatch
) -> None:
    from treestamp_web import app as app_module

    entered, release = Event(), Event()
    original = app_module.export_svg

    def blocked(data):
        entered.set()
        assert release.wait(5)
        return original(data)

    monkeypatch.setattr(app_module, "export_svg", blocked)
    with ThreadPoolExecutor(max_workers=1) as callers:
        pending = callers.submit(client.post, "/api/export/svg", json=export_body())
        try:
            assert entered.wait(5)
            assert client.get("/healthz").status_code == 200
            response = client.post("/api/export/svg", json=export_body())
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "svg_busy"
            assert response.headers["Retry-After"] == "1"
            assert not pending.done()
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 200


def test_svg_dirty_comparison_shares_export_worker(repo: Repo, monkeypatch) -> None:
    from treestamp_web import preview as preview_module

    fake, _ = svg_source(repo)
    entered, release = Event(), Event()
    original = preview_module.prepare_artifact_content

    def blocked(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(preview_module, "prepare_artifact_content", blocked)
    with (
        TestClient(create_app(make_config(), transport=transport_for(fake))) as client,
        ThreadPoolExecutor(max_workers=1) as callers,
    ):
        pending = callers.submit(
            client.get,
            "/api/preview",
            params={"url": "o/r", "document": "assets/tree.svg"},
        )
        try:
            assert entered.wait(5)
            assert client.get("/healthz").status_code == 200
            response = client.post("/api/export/svg", json=export_body())
            assert response.status_code == 503
            assert not pending.done()
        finally:
            release.set()
        assert pending.result(timeout=5).status_code == 200


def test_global_budget_applies_across_client_identities(fake, monkeypatch) -> None:
    from treestamp_web import app as app_module

    clock = Clock()
    pool = SvgWorkPool(clock)
    original = app_module.export_svg

    def expensive(data):
        clock.now += 3
        return original(data)

    monkeypatch.setattr(app_module, "export_svg", expensive)
    monkeypatch.setattr(app_module, "SvgWorkPool", lambda: pool)
    config = make_config(trust_proxy=True)
    with TestClient(create_app(config, transport=transport_for(fake))) as client:
        response = client.post(
            "/api/export/svg",
            json=export_body(),
            headers={"X-Forwarded-For": "192.0.2.1"},
        )
        assert response.status_code == 200
        response = client.post(
            "/api/export/svg",
            json=export_body(),
            headers={"X-Forwarded-For": "192.0.2.2"},
        )
        assert response.status_code == 503
        clock.now += int(response.headers["Retry-After"])
        assert client.post("/api/export/svg", json=export_body()).status_code == 200


def test_shutdown_waits_for_active_worker_and_stops_admission() -> None:
    pool = SvgWorkPool()
    entered, release = Event(), Event()

    def blocked() -> str:
        entered.set()
        assert release.wait(5)
        return "finished"

    async def exercise() -> None:
        pending = asyncio.create_task(pool.run(blocked))
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            closing = asyncio.create_task(pool.aclose())
            await asyncio.sleep(0)
            assert not closing.done()
            with pytest.raises(SvgBusyError):
                await pool.run(lambda: "must not run")
        finally:
            release.set()
        assert await pending == "finished"
        await closing
        with pytest.raises(SvgBusyError):
            await pool.run(lambda: "closed")

    asyncio.run(exercise())
