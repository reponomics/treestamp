import asyncio
import json
import time as real_time
from collections.abc import Callable

import httpx
import pytest

from treestamp import sources
from treestamp_web import github
from treestamp_web.github import (
    Budget,
    GitHubClient,
    NotFoundError,
    TooLargeError,
    UnavailableError,
    UpstreamTimeoutError,
)

from .conftest import Clock, make_config, transport_for_fake

SHA = "a" * 40
TREE = "b" * 40


def run(coro):  # type: ignore[no-untyped-def]
    return asyncio.run(coro)


def canned(
    responder: Callable[[httpx.Request], httpx.Response], **config: object
) -> GitHubClient:
    return GitHubClient(
        make_config(**config), transport=httpx.MockTransport(responder), clock=Clock()
    )


def ok(body: object, headers: dict[str, str] | None = None) -> httpx.Response:
    content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return httpx.Response(200, content=content, headers=headers or {})


def test_public_repository_reads_identity_and_branch() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/o/r"
        assert request.headers["accept"] == github.JSON_MEDIA
        return ok(
            {
                "id": 7,
                "full_name": "o/r",
                "private": False,
                "visibility": "public",
                "default_branch": "release/stable",
            }
        )

    client = canned(respond)
    assert run(client.public_repository("o", "r")) == github.PublicRepository(
        7, "release/stable"
    )
    assert client.calls == 1


@pytest.mark.parametrize(
    "body", [{}, [], {"default_branch": None}, {"default_branch": ""}]
)
def test_public_repository_rejects_missing_metadata(body: object) -> None:
    client = canned(lambda _: ok(body))
    with pytest.raises(UnavailableError, match="repository"):
        run(client.public_repository("o", "r"))


def test_budget_keeps_window_minimum_and_advances() -> None:
    budget = Budget()
    budget.observe(
        {
            "x-ratelimit-limit": "60",
            "x-ratelimit-remaining": "50",
            "x-ratelimit-reset": "100",
        }
    )
    budget.observe(
        {
            "x-ratelimit-limit": "60",
            "x-ratelimit-remaining": "48",
            "x-ratelimit-reset": "100",
        }
    )
    budget.observe(
        {
            "x-ratelimit-limit": "60",
            "x-ratelimit-remaining": "55",
            "x-ratelimit-reset": "100",
        }
    )
    assert budget.remaining == 48
    budget.observe(
        {
            "x-ratelimit-limit": "60",
            "x-ratelimit-remaining": "3",
            "x-ratelimit-reset": "50",
        }
    )
    assert budget.remaining == 48, "an older window is ignored"
    budget.observe(
        {
            "x-ratelimit-limit": "5000",
            "x-ratelimit-remaining": "4999",
            "x-ratelimit-reset": "200",
        }
    )
    assert budget.to_dict() == {"limit": 5000, "remaining": 4999, "reset": 200}
    budget.observe({"x-ratelimit-limit": "junk"})
    assert budget.remaining == 4999


def test_effective_reserve_scales_with_limit() -> None:
    budget = Budget(limit=60, remaining=5, reset=100)
    assert budget.effective_reserve(100) == 6
    assert budget.exhausted(100)
    budget.remaining = 6
    assert not budget.exhausted(100)
    assert Budget().effective_reserve(100) == 100
    assert not Budget().exhausted(100)
    assert Budget(limit=5000, remaining=99, reset=100).exhausted(100)
    assert Budget().retry_after(0) == 60
    assert Budget(reset=110).retry_after(100.5) == 10


def test_resolve_named_and_pinned_refs() -> None:
    seen: list[tuple[str, str]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, request.headers["accept"]))
        if request.url.path.endswith("/commits/feature/x"):
            return ok(SHA.encode())
        if request.url.path.endswith(f"/git/commits/{SHA}"):
            return ok({"sha": SHA, "tree": {"sha": TREE}})
        raise AssertionError(request.url)

    client = canned(responder)
    assert run(client.resolve("o", "r", "feature/x")) == github.Resolved(SHA, TREE)
    assert seen[0] == ("/repos/o/r/commits/feature/x", github.SHA_MEDIA)
    assert run(client.resolve("o", "r", SHA)) == github.Resolved(SHA, TREE)
    assert len(seen) == 3
    assert client.calls == 3


def test_resolve_rejects_unexpected_bodies() -> None:
    client = canned(lambda r: ok(b"not a sha"))
    with pytest.raises(UnavailableError, match="unexpected"):
        run(client.resolve("o", "r", "main"))
    client = canned(lambda r: ok({"sha": SHA}))
    with pytest.raises(UnavailableError, match="unexpected"):
        run(client.resolve("o", "r", SHA))
    client = canned(lambda r: ok(b"{not json"))
    with pytest.raises(UnavailableError, match="unexpected"):
        run(client.resolve("o", "r", SHA))


@pytest.mark.parametrize(
    ("status", "headers", "error", "message"),
    [
        (404, {}, NotFoundError, "not public"),
        (422, {}, NotFoundError, "ref not found"),
        (409, {}, NotFoundError, "empty"),
        (451, {}, NotFoundError, "legal"),
        (
            301,
            {"location": "https://api.github.com/repositories/1"},
            NotFoundError,
            "moved",
        ),
        (403, {"retry-after": "30"}, UnavailableError, "rate limiting"),
        (
            429,
            {
                "x-ratelimit-remaining": "0",
                "x-ratelimit-limit": "60",
                "x-ratelimit-reset": "1000100",
            },
            UnavailableError,
            "rate limiting",
        ),
        (403, {}, NotFoundError, "not accessible"),
        (500, {}, UnavailableError, "status 500"),
    ],
)
def test_status_mapping(
    status: int, headers: dict[str, str], error: type[Exception], message: str
) -> None:
    client = canned(lambda r: httpx.Response(status, headers=headers, content=b"{}"))
    with pytest.raises(error, match=message) as info:
        run(client.resolve("o", "r", SHA))
    exc = info.value
    assert isinstance(exc, github.GitHubError)
    if status == 403 and "retry-after" in headers:
        assert exc.retry_after == 30
    if status == 429:
        assert exc.retry_after == 101


def test_transport_failures_map_to_timeout_and_unavailable() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(UpstreamTimeoutError):
        run(canned(timeout).resolve("o", "r", SHA))

    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(UnavailableError, match="ConnectError"):
        run(canned(broken).resolve("o", "r", SHA))


def test_tree_rejects_truncated_oversized_and_malformed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {"path": "a", "mode": "100644", "type": "blob", "sha": SHA}
    client = canned(lambda r: ok({"tree": [row], "truncated": True}))
    with pytest.raises(TooLargeError, match="truncat"):
        run(client.tree("o", "r", TREE))
    monkeypatch.setattr(sources, "MAX_ENTRIES", 0)
    client = canned(lambda r: ok({"tree": [row], "truncated": False}))
    with pytest.raises(TooLargeError, match="entry limit"):
        run(client.tree("o", "r", TREE))
    monkeypatch.undo()
    client = canned(lambda r: ok({"tree": [{"path": "a"}]}))
    with pytest.raises(UnavailableError, match="tree row"):
        run(client.tree("o", "r", TREE))
    client = canned(lambda r: ok({"nope": 1}))
    with pytest.raises(UnavailableError, match="response for tree"):
        run(client.tree("o", "r", TREE))
    client = canned(lambda r: ok({"tree": [row]}))
    assert run(client.tree("o", "r", TREE)) == [
        sources.TreeRecord("a", "100644", "blob", SHA)
    ]


def test_body_caps_abandon_large_responses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(github, "BODY_CAP", 8)
    client = canned(lambda r: ok(b"x" * 9))
    with pytest.raises(TooLargeError, match="size limit"):
        run(client.blob("o", "r", SHA))
    monkeypatch.setattr(github, "TREE_BODY_CAP", 8)
    with pytest.raises(TooLargeError, match="size limit"):
        run(client.tree("o", "r", TREE))


def test_blob_uses_raw_media_type_and_token_header() -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.headers["accept"] == github.RAW_MEDIA
        assert request.headers["authorization"] == "Bearer secret"
        assert request.headers["user-agent"].startswith("treestamp-web/")
        return ok(b"target\n\xff")

    client = canned(responder, github_token="secret")
    assert run(client.blob("o", "r", SHA)) == b"target\n\xff"

    def anonymous(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return ok(b"t")

    assert run(canned(anonymous).blob("o", "r", SHA)) == b"t"


def test_budget_guard_refuses_uncached_work_but_seed_is_unguarded() -> None:
    headers = {
        "x-ratelimit-limit": "5000",
        "x-ratelimit-remaining": "10",
        "x-ratelimit-reset": "1000100",
    }

    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rate_limit":
            return ok(
                {
                    "resources": {
                        "core": {"limit": 5000, "remaining": 10, "reset": 1000100}
                    }
                },
                headers,
            )
        return ok(b"x", headers)

    client = canned(responder, github_rate_reserve=100)
    run(client.seed_budget())
    assert client.budget.remaining == 10
    with pytest.raises(UnavailableError, match="budget") as info:
        run(client.blob("o", "r", SHA))
    assert info.value.retry_after == 101
    run(client.seed_budget())
    assert client.calls == 2


def test_seed_budget_tolerates_failures_and_odd_bodies() -> None:
    client = canned(lambda r: httpx.Response(500))
    run(client.seed_budget())
    assert client.budget.limit is None
    client = canned(lambda r: ok({"resources": {"core": {"limit": "x"}}}))
    run(client.seed_budget())
    assert client.budget.limit is None
    client = canned(lambda r: ok(b"[]"))
    run(client.seed_budget())
    assert client.budget.limit is None
    run(client.aclose())


@pytest.mark.parametrize("offset", [0, 1])
def test_budget_reset_coordinates_one_probe_for_concurrent_requests(offset):
    clock = Clock()
    reset = clock.now + 10
    probes = 0
    blobs = 0

    async def responder(request):
        nonlocal probes, blobs
        if request.url.path == "/rate_limit":
            probes += 1
            await asyncio.sleep(0)
            return ok(
                {
                    "resources": {
                        "core": {
                            "limit": 5000,
                            "remaining": 4900,
                            "reset": reset + 3600,
                        }
                    }
                }
            )
        blobs += 1
        return ok(b"target")

    client = GitHubClient(
        make_config(github_rate_reserve=100),
        transport=httpx.MockTransport(responder),
        clock=clock,
    )
    client.budget = Budget(limit=5000, remaining=10, reset=int(reset))
    with pytest.raises(UnavailableError):
        run(client.blob("o", "r", SHA))
    assert probes == blobs == 0
    clock.now = reset + offset

    async def burst():
        return await asyncio.gather(*(client.blob("o", "r", SHA) for _ in range(12)))

    assert run(burst()) == [b"target"] * 12
    assert probes == 1 and blobs == 12


def test_failed_budget_probe_can_recover_without_restart():
    clock = Clock()
    probes = 0

    def responder(request):
        nonlocal probes
        if request.url.path == "/rate_limit":
            probes += 1
            if probes == 1:
                return httpx.Response(503)
            return ok(
                {
                    "resources": {
                        "core": {
                            "limit": 5000,
                            "remaining": 4900,
                            "reset": clock.now + 3600,
                        }
                    }
                }
            )
        return ok(b"target")

    client = GitHubClient(
        make_config(github_rate_reserve=100),
        transport=httpx.MockTransport(responder),
        clock=clock,
    )
    client.budget = Budget(limit=5000, remaining=10, reset=int(clock.now - 1))
    with pytest.raises(UnavailableError) as failure:
        run(client.blob("o", "r", SHA))
    assert failure.value.retry_after >= 5
    clock.now += 4
    with pytest.raises(UnavailableError):
        run(client.blob("o", "r", SHA))
    assert probes == 1
    clock.now += 1
    assert run(client.blob("o", "r", SHA)) == b"target" and probes == 2


@pytest.mark.parametrize(
    "changes",
    [
        {"private": True},
        {"visibility": "private"},
        {"visibility": "internal"},
        {"private": None},
        {"private": "false"},
        {"visibility": None},
    ],
)
def test_acquisition_requires_explicit_public_metadata(changes):
    metadata = {
        "id": 7,
        "full_name": "o/r",
        "default_branch": "main",
        "private": False,
        "visibility": "public",
        **changes,
    }
    client = canned(lambda _: ok(metadata))
    with pytest.raises(NotFoundError, match="not public"):
        run(client.public_repository("o", "r"))


@pytest.mark.parametrize(
    "changes",
    [
        {"id": True},
        {"id": None},
        {"id": 0},
        {"full_name": "another/repo"},
        {"full_name": None},
        {"full_name": {}},
    ],
)
def test_acquisition_requires_matching_repository_identity(changes):
    metadata = {
        "id": 7,
        "full_name": "o/r",
        "default_branch": "main",
        "private": False,
        "visibility": "public",
        **changes,
    }
    client = canned(lambda _: ok(metadata))
    with pytest.raises(UnavailableError, match="repository"):
        run(client.public_repository("o", "r"))


def test_forbidden_with_rate_headers_is_rate_limiting() -> None:
    headers = {
        "x-ratelimit-limit": "60",
        "x-ratelimit-remaining": "0",
        "x-ratelimit-reset": "1000100",
    }
    client = canned(lambda r: httpx.Response(403, headers=headers, content=b"{}"))
    with pytest.raises(UnavailableError, match="rate limiting") as info:
        run(client.resolve("o", "r", SHA))
    assert info.value.retry_after == 101


# ---------- GitHub App credential


def rsa_keys() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = (
        key.public_key()
        .public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        .decode()
    )
    return private, public


def test_app_credential_mints_verifies_caches_and_refreshes() -> None:
    private, public = rsa_keys()
    clock = Clock(real_time.time())
    seen: list[tuple[str, str, str]] = []
    issued = 0

    def responder(request: httpx.Request) -> httpx.Response:
        nonlocal issued
        seen.append(
            (request.method, request.url.path, request.headers.get("authorization", ""))
        )
        if request.method == "POST":
            assert request.url.path == "/app/installations/777/access_tokens"
            import jwt as pyjwt

            claims = pyjwt.decode(
                request.headers["authorization"].removeprefix("Bearer "),
                public,
                algorithms=["RS256"],
                leeway=7200,  # the test clock runs ahead of real time
            )
            assert claims["iss"] == "Iv1.example"
            assert claims["exp"] - claims["iat"] == github.JWT_LIFETIME + 60
            issued += 1
            expires = real_time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", real_time.gmtime(clock.now + 3600)
            )
            return httpx.Response(
                201, json={"token": f"ghs_{issued}", "expires_at": expires}
            )
        return ok({"sha": SHA, "tree": {"sha": TREE}})

    client = GitHubClient(
        make_config(
            github_app_client_id="Iv1.example",
            github_app_installation_id="777",
            github_app_private_key=private,
        ),
        transport=httpx.MockTransport(responder),
        clock=clock,
    )
    assert client.credential == "app"
    run(client.resolve("o", "r", "a" * 40))
    assert seen[0][0] == "POST" and seen[1][2] == "Bearer ghs_1"
    run(client.resolve("o", "r", "b" * 40))
    assert issued == 1, "the token is reused while fresh"
    clock.now += 3600 - 60  # inside the refresh margin
    run(client.resolve("o", "r", "c" * 40))
    assert issued == 2, "a token near expiry is replaced before use"
    assert client.calls == 5


def test_app_credential_retries_once_after_401_and_reports_failures() -> None:
    private, _ = rsa_keys()
    issued = 0
    calls: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        nonlocal issued
        calls.append(request.headers.get("authorization", ""))
        if request.method == "POST":
            issued += 1
            return httpx.Response(201, json={"token": f"ghs_{issued}"})
        if request.headers.get("authorization") == "Bearer ghs_1":
            return httpx.Response(401, content=b"{}")
        return ok({"sha": SHA, "tree": {"sha": TREE}})

    client = GitHubClient(
        make_config(
            github_app_client_id="Iv1.example",
            github_app_installation_id="777",
            github_app_private_key=private,
        ),
        transport=httpx.MockTransport(responder),
        clock=Clock(),
    )
    assert run(client.resolve("o", "r", SHA)) == github.Resolved(SHA, TREE)
    assert issued == 2 and calls[-1] == "Bearer ghs_2"

    failing = GitHubClient(
        make_config(
            github_app_client_id="Iv1.example",
            github_app_installation_id="777",
            github_app_private_key=private,
        ),
        transport=httpx.MockTransport(lambda r: httpx.Response(403, content=b"{}")),
        clock=Clock(),
    )
    with pytest.raises(UnavailableError, match="token exchange failed with status 403"):
        run(failing.resolve("o", "r", SHA))
    odd = GitHubClient(
        make_config(
            github_app_client_id="Iv1.example",
            github_app_installation_id="777",
            github_app_private_key=private,
        ),
        transport=httpx.MockTransport(lambda r: httpx.Response(201, content=b"[]")),
        clock=Clock(),
    )
    with pytest.raises(
        UnavailableError, match="unexpected GitHub response for installation token"
    ):
        run(odd.resolve("o", "r", SHA))
    assert (
        GitHubClient(
            make_config(), transport=httpx.MockTransport(ok), clock=Clock()
        ).credential
        == "none"
    )
    assert (
        GitHubClient(
            make_config(github_token="t"),
            transport=httpx.MockTransport(ok),
            clock=Clock(),
        ).credential
        == "token"
    )


def test_app_credential_against_the_fake(repo_fake_with_app) -> None:  # type: ignore[no-untyped-def]
    fake, private = repo_fake_with_app
    from treestamp_web.preview import PreviewService, parse_request

    config = make_config(
        github_app_client_id="Iv1.example",
        github_app_installation_id="12345",
        github_app_private_key=private,
    )
    clock = Clock(real_time.time())  # the fake verifies the JWT against real time
    client = GitHubClient(config, transport=transport_for_fake(fake), clock=clock)
    service = PreviewService(client, config, clock)
    result = asyncio.run(service.preview(parse_request({"url": "o/r"})))
    assert result.commit and fake.tokens_issued == 1
    bad = GitHubClient(
        make_config(
            github_app_client_id="Iv1.example",
            github_app_installation_id="12345",
            github_app_private_key=rsa_keys()[0],
        ),
        transport=transport_for_fake(fake),
        clock=Clock(real_time.time()),
    )
    with pytest.raises(UnavailableError, match="status 401"):
        run(bad.resolve("o", "r", "HEAD"))
