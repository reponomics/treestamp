"""Visitor rate-limit identity across Cloudflare, Fly, and direct requests."""

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from treestamp_web.app import _client_identity, create_app
from treestamp_web.config import Config, ConfigError
from treestamp_web.localgit import FakeGitHub

from .conftest import Clock, make_config, transport_for


def cloudflare_config(**overrides: object) -> Config:
    return make_config(
        trust_proxy=True,
        client_ip_header="Fly-Client-IP",
        cloudflare_proxy_cidrs="173.245.48.0/20, 2606:4700::/32",
        **overrides,
    )


def identity(headers: list[tuple[str, str]], config: Config | None = None) -> str:
    request = Request(
        {
            "type": "http",
            "client": ("10.0.0.2", 12345),
            "headers": [
                (name.lower().encode(), value.encode()) for name, value in headers
            ],
        }
    )
    return _client_identity(request, config or cloudflare_config())


@pytest.mark.parametrize(
    ("peer", "visitor", "expected"),
    [
        ("173.245.48.1", "198.51.100.2", "198.51.100.2"),
        ("2606:4700::1", "2001:0db8:0:0::2", "2001:db8::2"),
        ("2606:4700::1", "198.51.100.2", "198.51.100.2"),
        ("173.245.48.1", "2001:db8::2", "2001:db8::2"),
        ("173.245.64.1", "198.51.100.2", "173.245.64.1"),
        ("203.0.113.2", "198.51.100.2", "203.0.113.2"),
        ("2001:db8::1", "198.51.100.2", "2001:db8::1"),
    ],
)
def test_visitor_requires_a_trusted_cloudflare_peer(peer, visitor, expected):
    assert (
        identity([("Fly-Client-IP", peer), ("CF-Connecting-IP", visitor)]) == expected
    )


@pytest.mark.parametrize("header", ["Fly-Client-IP", "CF-Connecting-IP"])
@pytest.mark.parametrize(
    "invalid",
    ["", "unknown", "198.51.100.2, 198.51.100.3", "198.51.100.2:443", "fe80::1%eth0"],
)
def test_invalid_header_cannot_supply_identity(header, invalid):
    headers = {"Fly-Client-IP": "173.245.48.1", "CF-Connecting-IP": "198.51.100.2"}
    headers[header] = invalid
    expected = "10.0.0.2" if header == "Fly-Client-IP" else "173.245.48.1"
    assert identity(list(headers.items())) == expected


@pytest.mark.parametrize("header", ["Fly-Client-IP", "CF-Connecting-IP"])
def test_duplicate_headers_cannot_supply_identity(header):
    headers = [("Fly-Client-IP", "173.245.48.1"), ("CF-Connecting-IP", "198.51.100.2")]
    headers.append((header, "198.51.100.3"))
    expected = "10.0.0.2" if header == "Fly-Client-IP" else "173.245.48.1"
    assert identity(headers) == expected


def test_missing_headers_use_peer_or_connection_identity():
    assert identity([]) == "10.0.0.2"
    assert identity([("CF-Connecting-IP", "198.51.100.2")]) == "10.0.0.2"
    assert identity([("Fly-Client-IP", "173.245.48.1")]) == "173.245.48.1"
    request = Request({"type": "http", "headers": []})
    assert _client_identity(request, cloudflare_config()) == "unknown"


def test_worker_subrequests_cannot_choose_visitor_identity():
    headers = [
        ("Fly-Client-IP", "173.245.48.1"),
        ("CF-Connecting-IP", "198.51.100.2"),
        ("CF-Worker", "untrusted.example"),
    ]
    assert identity(headers) == "173.245.48.1"


def test_cloudflare_mode_is_opt_in_and_keeps_existing_proxy_modes():
    headers = [("Fly-Client-IP", "173.245.48.1"), ("CF-Connecting-IP", "198.51.100.2")]
    assert identity(headers, Config()) == "10.0.0.2"
    direct_fly = Config(trust_proxy=True, client_ip_header="Fly-Client-IP")
    assert identity(headers, direct_fly) == "173.245.48.1"
    assert (
        identity(
            [("X-Forwarded-For", "198.51.100.2, 10.0.0.1")], Config(trust_proxy=True)
        )
        == "198.51.100.2"
    )


def test_cloudflare_config_from_env():
    config = Config.from_env(
        {
            "TRUST_PROXY": "1",
            "CLIENT_IP_HEADER": "Fly-Client-IP",
            "CLOUDFLARE_PROXY_CIDRS": "173.245.48.0/20,2606:4700::/32",
        }
    )
    assert [str(network) for network in config.cloudflare_networks] == [
        "173.245.48.0/20",
        "2606:4700::/32",
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"TRUST_PROXY": "0"},
        {"CLIENT_IP_HEADER": "X-Forwarded-For"},
        {"CLOUDFLARE_PROXY_CIDRS": "not-a-network"},
        {"CLOUDFLARE_PROXY_CIDRS": "173.245.48.0/20,"},
        {"CLOUDFLARE_PROXY_CIDRS": "173.245.48.1/20"},
        {"CLOUDFLARE_PROXY_CIDRS": "0.0.0.0/0"},
        {"CLOUDFLARE_PROXY_CIDRS": "::/0"},
    ],
)
def test_cloudflare_config_rejects_unsafe_or_invalid_setup(overrides):
    env = {
        "TRUST_PROXY": "1",
        "CLIENT_IP_HEADER": "Fly-Client-IP",
        "CLOUDFLARE_PROXY_CIDRS": "173.245.48.0/20",
    }
    env.update(overrides)
    with pytest.raises(ConfigError, match="CLOUDFLARE_PROXY_CIDRS"):
        Config.from_env(env)


def test_rate_limits_separate_cloudflare_visitors_and_ignore_direct_spoofs(
    fake: FakeGitHub,
) -> None:
    app = create_app(
        cloudflare_config(rate_limit_per_minute=1),
        transport=transport_for(fake),
        clock=Clock(),
    )
    with TestClient(app) as client:

        def preview(peer: str, visitor: str) -> int:
            return client.get(
                "/api/preview",
                params={"url": "o/r"},
                headers={"Fly-Client-IP": peer, "CF-Connecting-IP": visitor},
            ).status_code

        assert preview("173.245.48.1", "198.51.100.2") == 200
        assert preview("173.245.48.1", "198.51.100.3") == 200
        assert preview("173.245.48.1", "198.51.100.2") == 429
        assert preview("203.0.113.1", "198.51.100.4") == 200
        assert preview("203.0.113.1", "198.51.100.5") == 429
