"""Fly affinity keeps healthy sessions local and bounds recovery after failure."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from treestamp_web.app import create_app
from treestamp_web.config import Config, ConfigError
from treestamp_web.routing import COOKIE, MAX_REPLAY_BODY

from .conftest import Clock, make_config, transport_for

A = "aaaaaaaaaaaaaa"
B = "bbbbbbbbbbbbbb"


def machine(fake, name, clock=None, **overrides):
    return TestClient(
        create_app(
            make_config(fly_session_routing=True, fly_machine_id=name, **overrides),
            transport=transport_for(fake),
            clock=clock or Clock(),
        ),
        base_url="https://testserver",
        follow_redirects=False,
    )


def operation(preview):
    return {
        "owner": "o",
        "repo": "r",
        "ref": preview["ref"]["commit"],
        "root": preview["root"],
        "document": preview["document"],
        "state": preview["state"],
        "op": {"type": "annotate", "path": "", "text": "kept note"},
    }


def owner_header(name):
    return {"Cookie": f"{COOKIE}={name}"}


def test_two_machines_replay_operations_to_the_snapshot_owner(fake):
    with machine(fake, A) as first, machine(fake, B) as second:
        loaded = first.get("/api/preview", params={"url": "o/r"})
        assert loaded.status_code == 200
        cookie = loaded.headers["set-cookie"]
        assert cookie.startswith(f"{COOKIE}={A};")
        assert "HttpOnly" in cookie and "Secure" in cookie
        assert "Path=/" in cookie and "SameSite=lax" in cookie
        assert "Domain=" not in cookie and "Max-Age=" not in cookie
        assert loaded.headers["cache-control"] == "private, no-store"
        assert first.cookies.get(COOKIE) == A
        body = operation(loaded.json())
        calls = second.app.state.client.calls

        forwarded = second.post("/api/op", headers=owner_header(A), json=body)
        assert forwarded.status_code == 307
        assert forwarded.headers["fly-replay"] == (
            f"instance={A};timeout=2s;fallback=prefer_self"
        )
        assert "set-cookie" not in forwarded.headers
        assert second.app.state.client.calls == calls
        assert second.app.state.service.stats()["trees"] == 0

        # Model the Fly proxy replaying the unchanged body to its requested owner.
        replayed = first.post(
            "/api/op",
            headers={**owner_header(A), "Fly-Replay-Src": f"instance={B}"},
            json=body,
        )
        assert replayed.status_code == 200
        assert "kept note" in replayed.json()["region"]
        assert "fly-replay" not in replayed.headers
        assert "set-cookie" not in replayed.headers


def test_failed_owner_returns_snapshot_error_then_fresh_load_rebinds(fake):
    with machine(fake, A) as first:
        original = first.get("/api/preview", params={"url": "o/r"}).json()
    original_state = deepcopy(original)
    body = operation(original)
    with machine(fake, B) as second:
        calls = second.app.state.client.calls
        forwarded = second.post("/api/op", headers=owner_header(A), json=body)
        assert forwarded.status_code == 307
        fallback = {
            **owner_header(A),
            "Fly-Replay-Failed": f"instance={A};reason=no_candidate;replay_source={B}",
        }
        lost = second.post("/api/op", headers=fallback, json=body)
        assert lost.status_code == 410
        assert lost.json()["error"]["code"] == "snapshot_unavailable"
        assert "fly-replay" not in lost.headers
        assert "set-cookie" not in lost.headers
        assert second.app.state.client.calls == calls
        assert original == original_state

        failed_load = second.post(
            "/api/preview", headers=fallback, json={"url": "o/r", "document": "missing"}
        )
        assert failed_load.status_code == 404
        assert "set-cookie" not in failed_load.headers
        assert "fly-replay" not in failed_load.headers

        fresh = second.post("/api/preview", headers=fallback, json={"url": "o/r"})
        assert fresh.status_code == 200
        assert second.cookies.get(COOKIE) == B
        assert "fly-replay" not in fresh.headers
        restored = second.post("/api/op", json=operation(fresh.json()))
        assert restored.status_code == 200
        assert "kept note" in restored.json()["region"]


def test_replayed_url_load_stays_with_the_healthy_owner(fake):
    with machine(fake, A) as first, machine(fake, B) as second:
        first.get("/api/preview", params={"url": "o/r"})
        forwarded = second.get(
            "/api/preview", params={"url": "o/r"}, headers=owner_header(A)
        )
        assert forwarded.status_code == 307
        replayed = first.get(
            "/api/preview",
            params={"url": "o/r"},
            headers={**owner_header(A), "Fly-Replay-Src": f"instance={B}"},
        )
        assert replayed.status_code == 200
        assert first.cookies.get(COOKIE) == A
        assert second.app.state.service.stats()["trees"] == 0


@pytest.mark.parametrize(
    "marker",
    ["Fly-Replay-Src", "Fly-Replay-Failed", "Fly-Preferred-Instance-Unavailable"],
)
def test_replay_markers_stop_loops_without_granting_snapshot_access(fake, marker):
    with machine(fake, A) as first, machine(fake, B) as second:
        loaded = first.get("/api/preview", params={"url": "o/r"}).json()
        calls = second.app.state.client.calls
        response = second.post(
            "/api/op",
            json=operation(loaded),
            headers={**owner_header(A), marker: "malformed-client-supplied-value"},
        )
        assert response.status_code == 410
        assert response.json()["error"]["code"] == "snapshot_unavailable"
        assert "fly-replay" not in response.headers
        assert second.app.state.client.calls == calls


@pytest.mark.parametrize(
    "value",
    [
        "",
        "not-a-machine",
        "a" * 13,
        "a" * 15,
        "A" * 14,
        f'"{A};app=other"',
        f"{A},app=other",
        f"{A}; {COOKIE}={B}",
    ],
)
def test_malformed_cookies_cannot_inject_replay_targets(fake, value):
    with machine(fake, A) as first:
        response = first.get(
            "/api/preview", params={"url": "o/r"}, headers=owner_header(value)
        )
        assert response.status_code == 200
        assert "fly-replay" not in response.headers
        assert first.cookies.get(COOKIE) == A


def test_only_api_requests_are_routed_and_invalid_operations_keep_validation(fake):
    with machine(fake, B) as second:
        headers = owner_header(A)
        for path in ("/", "/healthz", "/static/app.js", "/api/missing"):
            response = second.get(path, headers=headers)
            assert "fly-replay" not in response.headers
            assert "set-cookie" not in response.headers
        invalid = second.post(
            "/api/op", headers={**headers, "Fly-Replay-Src": "client"}, json={}
        )
        assert invalid.status_code == 400
        assert "fly-replay" not in invalid.headers


def test_oversized_request_is_rejected_before_replay(fake):
    with machine(fake, B, max_state_bytes=32) as second:
        for content in (b"x" * 33, iter([b"x" * 20, b"y" * 20])):
            response = second.post("/api/op", headers=owner_header(A), content=content)
            assert response.status_code == 413
            assert response.json()["error"]["code"] == "state_too_large"
            assert "fly-replay" not in response.headers


def test_affinity_does_not_extend_snapshot_expiry(fake):
    clock = Clock()
    with machine(fake, A, clock) as first, machine(fake, B, clock) as second:
        loaded = first.get("/api/preview", params={"url": "o/r"}).json()
        clock.now += 3600
        forwarded = second.post(
            "/api/op", headers=owner_header(A), json=operation(loaded)
        )
        assert forwarded.status_code == 307
        expired = first.post(
            "/api/op",
            headers={**owner_header(A), "Fly-Replay-Src": f"instance={B}"},
            json=operation(loaded),
        )
        assert expired.status_code == 410
        assert expired.json()["error"]["code"] == "snapshot_unavailable"
        assert "fly-replay" not in expired.headers
        assert "set-cookie" not in expired.headers
        fresh = first.get("/api/preview", params={"url": "o/r"})
        assert fresh.status_code == 200
        assert first.post("/api/op", json=operation(fresh.json())).status_code == 200


def test_same_machine_restart_reports_lost_snapshot_without_a_loop(fake):
    with machine(fake, A) as before:
        loaded = before.get("/api/preview", params={"url": "o/r"}).json()
    with machine(fake, A) as after:
        response = after.post(
            "/api/op", headers=owner_header(A), json=operation(loaded)
        )
        assert response.status_code == 410
        assert "fly-replay" not in response.headers
        assert "set-cookie" not in response.headers


def test_routing_is_opt_in(fake):
    config = make_config(fly_machine_id=A)
    with TestClient(create_app(config, transport=transport_for(fake))) as client:
        response = client.get(
            "/api/preview", params={"url": "o/r"}, headers=owner_header(B)
        )
        assert response.status_code == 200
        assert "fly-replay" not in response.headers
        assert "set-cookie" not in response.headers


def test_routing_environment_validation():
    config = Config.from_env({"FLY_SESSION_ROUTING": "true", "FLY_MACHINE_ID": A})
    assert config.session_machine_id == A
    assert Config.from_env({"FLY_MACHINE_ID": "not-on-fly"}).session_machine_id is None
    for name in (None, "", "invalid", f"{A};app=other"):
        env = {"FLY_SESSION_ROUTING": "true"}
        if name is not None:
            env["FLY_MACHINE_ID"] = name
        with pytest.raises(ConfigError, match="FLY_MACHINE_ID"):
            Config.from_env(env)
    with pytest.raises(ConfigError, match="MAX_STATE_BYTES"):
        Config.from_env(
            {
                "FLY_SESSION_ROUTING": "true",
                "FLY_MACHINE_ID": A,
                "MAX_STATE_BYTES": str(MAX_REPLAY_BODY + 1),
            }
        )
