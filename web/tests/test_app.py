from collections.abc import Iterator
from importlib.metadata import version
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from treestamp_web.app import SECURITY_HEADERS, create_app
from treestamp_web.config import Config, ConfigError
from treestamp_web.localgit import FakeGitHub, FakeOptions

from .conftest import Clock, Repo, make_config, transport_for


def test_healthz_reports_versions_budget_and_cache(client: TestClient) -> None:
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["web"] == version("treestamp-web") and body["package"]
    assert body["token_configured"] is False
    assert body["budget"]["limit"] == 60 and body["budget"]["remaining"] == 59
    assert body["cache"] == {
        "trees": 0,
        "tree_rows": 0,
        "blobs": 0,
        "refs": 0,
    }
    for name, value in SECURITY_HEADERS.items():
        assert client.get("/healthz").headers[name] == value


def test_preview_contract(client: TestClient) -> None:
    response = client.get("/api/preview", params={"url": "o/r"})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "repository",
        "ref",
        "root",
        "document",
        "loaded",
        "settings",
        "dirty",
        "notice",
        "entries",
        "root_children",
        "tree",
        "region",
        "warnings",
        "permalink",
        "state",
        "rows",
    }
    assert body["repository"] == {
        "owner": "o",
        "name": "r",
        "url": "https://github.com/o/r",
        "default_branch": "main",
    }
    assert body["region"].endswith("<!-- treestamp:end -->\n")
    assert body["permalink"].startswith(f"/o/r@{body['ref']['commit']}?")
    assert body["root_children"] == 6 and body["dirty"]
    assert client.get("/healthz").json()["cache"]["trees"] == 1


def test_application_logs_do_not_include_rate_limit_identity(fake, caplog):
    caplog.set_level("INFO", logger="treestamp_web")
    app = create_app(make_config(trust_proxy=True), transport=transport_for(fake))
    with TestClient(app) as client:
        headers = {"X-Forwarded-For": "198.51.100.42"}
        assert (
            client.get(
                "/api/preview", params={"url": "o/r"}, headers=headers
            ).status_code
            == 200
        )
        assert (
            client.get(
                "/api/preview", params={"url": "invalid"}, headers=headers
            ).status_code
            == 400
        )
    records = [
        record.message for record in caplog.records if record.name == "treestamp_web"
    ]
    assert len(records) == 2
    assert all("198.51.100.42" not in message for message in records)


def test_api_cannot_authorize_snapshot_by_tampering_with_state(client):
    first = client.post("/api/preview", json={"url": "o/r"}).json()
    arbitrary = "f" * 40
    first["state"]["source"]["commit"] = arbitrary
    body = {
        "owner": "o",
        "repo": "r",
        "ref": arbitrary,
        "root": first["root"],
        "document": first["document"],
        "state": first["state"],
        "op": {"type": "restore"},
    }
    calls = client.app.state.client.calls
    response = client.post("/api/op", json=body)
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "snapshot_unavailable"
    assert client.app.state.client.calls == calls


@pytest.mark.parametrize(
    ("params", "status", "code"),
    [
        ({}, 400, "invalid_link"),
        ({"url": "o/r", "depth": "-1"}, 400, "invalid_settings"),
        ({"url": "o/r", "root": "top.txt"}, 422, "curation"),
        ({"owner": "o", "repo": "r", "ref": "no-branch"}, 400, "invalid_link"),
        ({"owner": "o", "repo": "r", "ref": "f" * 40}, 410, "snapshot_unavailable"),
    ],
)
def test_error_statuses(
    client: TestClient, params: dict[str, str], status: int, code: str
) -> None:
    response = client.get("/api/preview", params=params)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "retry_after" not in response.json()["error"]


def options_client(
    options: FakeOptions, fake: FakeGitHub, **config: object
) -> TestClient:
    fake.options = options
    return TestClient(
        create_app(make_config(**config), transport=transport_for(fake), clock=Clock())
    )


def test_upstream_failures(fake: FakeGitHub) -> None:
    with options_client(FakeOptions(truncated=True), fake) as client:
        response = client.get("/api/preview", params={"url": "o/r"})
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "too_large"
    with options_client(FakeOptions(empty=True), fake) as client:
        assert client.get("/api/preview", params={"url": "o/r"}).status_code == 404
    with options_client(FakeOptions(only="x/y"), fake) as client:
        assert client.get("/api/preview", params={"url": "o/r"}).status_code == 404
        assert client.get("/api/preview", params={"url": "x/y"}).status_code == 200
    with options_client(FakeOptions(rate_limit_after=1), fake) as client:
        response = client.get("/api/preview", params={"url": "o/r"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "upstream_unavailable"
        assert response.headers["Retry-After"] == str(
            response.json()["error"]["retry_after"]
        )
    with options_client(FakeOptions(limit=60), fake, github_rate_reserve=100) as client:
        response = client.get("/api/preview", params={"url": "o/r"})
        assert response.status_code == 200, (
            "the effective reserve is 6 at a limit of 60"
        )


def test_timeout_maps_to_504(fake: FakeGitHub) -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    app = create_app(make_config(), transport=httpx.MockTransport(slow), clock=Clock())
    with TestClient(app) as client:
        response = client.get("/api/preview", params={"url": "o/r"})
        assert response.status_code == 504
        assert response.json()["error"]["code"] == "upstream_timeout"
        assert client.get("/healthz").json()["budget"]["limit"] is None


def test_rate_limit_and_client_identity(fake: FakeGitHub) -> None:
    clock = Clock()
    config = make_config(
        rate_limit_per_minute=2, trust_proxy=True, client_ip_header="Fly-Client-IP"
    )
    with TestClient(
        create_app(config, transport=transport_for(fake), clock=clock)
    ) as client:
        for _ in range(2):
            assert client.get("/api/preview", params={"url": "o/r"}).status_code == 200
        response = client.get("/api/preview", params={"url": "o/r"})
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limited"
        assert response.headers["Retry-After"] == "30"
        other = {"Fly-Client-IP": "203.0.113.9, 10.0.0.1"}
        assert (
            client.get("/api/preview", params={"url": "o/r"}, headers=other).status_code
            == 200
        )
        clock.now += 31
        assert client.get("/api/preview", params={"url": "o/r"}).status_code == 200


def test_pages_and_static_files(client: TestClient) -> None:
    for path in ("/", "/o/r", "/o/r@" + "0" * 40):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert '<form id="form"' in response.text
        assert response.headers["Content-Security-Policy"] == "default-src 'self'"
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200
    icon = client.get("/favicon.ico")
    assert icon.status_code == 200 and icon.headers["content-type"].startswith(
        "image/x-icon"
    )
    assert icon.content[:4] == b"\x00\x00\x01\x00", "an ICO header"
    assert icon.headers["Cache-Control"] == "public, max-age=86400"
    for name in ("favicon-32.png", "apple-touch-icon.png", "icon-512.png"):
        assert client.get(f"/static/{name}").content[:8] == b"\x89PNG\r\n\x1a\n"
    for name in ("logo.webp", "logo-dark.webp"):
        assert client.get(f"/static/{name}").content[:4] == b"RIFF", "a WebP header"
    svg = client.get("/static/favicon.svg")
    assert svg.status_code == 200 and svg.content.startswith(b"<svg")
    assert 'type="image/svg+xml" href="/static/favicon.svg"' in client.get("/").text
    assert client.get("/static/missing.js").status_code == 404


def test_public_base_url_makes_permalinks_absolute(fake: FakeGitHub) -> None:
    config = make_config(public_base_url="https://preview.example")
    with TestClient(
        create_app(config, transport=transport_for(fake), clock=Clock())
    ) as client:
        body = client.get("/api/preview", params={"url": "o/r"}).json()
        assert body["permalink"].startswith("https://preview.example/o/r@")


def test_config_from_env() -> None:
    env = {
        "PORT": "9000",
        "GITHUB_TOKEN": "t",
        "GITHUB_API_URL": "https://api.example/",
        "TRUST_PROXY": "1",
        "REQUEST_TIMEOUT_SECONDS": "2.5",
        "LOG_LEVEL": "debug",
        "PUBLIC_BASE_URL": "",
    }
    config = Config.from_env(env)
    assert config.port == 9000 and config.github_token == "t"
    assert config.github_api_url == "https://api.example"
    assert config.trust_proxy is True and config.request_timeout_seconds == 2.5
    assert config.public_base_url is None
    assert Config.from_env({"TRUST_PROXY": "no"}).trust_proxy is False
    assert Config.from_env({"LOG_LEVEL": "INFO"}).log_level == "info"
    for bad in (
        {"PORT": "x"},
        {"PORT": "70000"},
        {"PORT": "-1"},
        {"TRUST_PROXY": "maybe"},
        {"REQUEST_TIMEOUT_SECONDS": "0"},
        {"LOG_LEVEL": "loud"},
        {"GITHUB_API_URL": "ftp://x"},
        {"PUBLIC_BASE_URL": "x"},
    ):
        with pytest.raises(ConfigError):
            Config.from_env(bad)


@pytest.fixture
def unused(fake: FakeGitHub) -> Iterator[None]:
    yield


def test_reserved_prefixes_are_not_pages(client: TestClient) -> None:
    for path in ("/api/anything", "/static/x/y", "/healthz/extra"):
        response = client.get(path)
        assert response.status_code == 404, path
    assert client.get("/api/anything").json()["error"]["code"] == "not_found"
    assert client.get("/healthz/extra").headers["X-Content-Type-Options"] == "nosniff"


def test_unknown_upstream_failures_default_retry_after(fake: FakeGitHub) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/rate_limit":
            return httpx.Response(200, json={})
        return httpx.Response(500)

    app = create_app(
        make_config(), transport=httpx.MockTransport(broken), clock=Clock()
    )
    with TestClient(app) as client:
        response = client.get("/api/preview", params={"url": "o/r"})
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "60"
        assert response.json()["error"]["retry_after"] == 60


def test_operation_endpoint_contract_and_limits(fake: FakeGitHub) -> None:
    clock = Clock()
    config = make_config(op_rate_limit_per_minute=2, max_state_bytes=2000)
    with TestClient(
        create_app(config, transport=transport_for(fake), clock=clock)
    ) as client:
        first = client.get("/api/preview", params={"url": "o/r"}).json()
        body = {
            "owner": "o",
            "repo": "r",
            "ref": first["ref"]["commit"],
            "root": ".",
            "state": first["state"],
            "reveal": True,
            "op": {"type": "toggle", "path": "sub"},
        }
        response = client.post("/api/op", json=body)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["state"]["curation"]["expanded"] == ["sub"]
        assert any(row["path"] == "sub/other.txt" for row in data["rows"])
        assert response.headers["Cache-Control"] == "no-cache"
        assert (
            client.post(
                "/api/op",
                content=b"{not json",
                headers={"content-type": "application/json"},
            ).status_code
            == 400
        )
        response = client.post("/api/op", json=body)
        assert (
            response.status_code == 429
            and response.json()["error"]["code"] == "rate_limited"
        )
        clock.now += 31
        big = dict(body, state=dict(first["state"], annotations={"": "x" * 3000}))
        response = client.post("/api/op", json=big)
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "state_too_large"
        clock.now += 31
        oversized = client.post(
            "/api/op",
            content=b"{}",
            headers={"content-length": "999999", "content-type": "application/json"},
        )
        assert oversized.status_code == 413, "declared length is refused before reading"
        clock.now += 31
        nested = client.post(
            "/api/op",
            content=b"[" * 1500,
            headers={"content-type": "application/json"},
        )
        assert nested.status_code == 400


def test_check_endpoint_is_not_an_editor_action(client: TestClient) -> None:
    assert client.get("/api/check", params={"url": "o/r"}).status_code == 404


def test_healthz_reports_the_credential_and_config_rejects_partial_app_settings(
    fake: FakeGitHub,
) -> None:
    from .test_github import rsa_keys

    private, _ = rsa_keys()
    config = make_config(
        github_app_client_id="1",
        github_app_installation_id="2",
        github_app_private_key=private,
    )
    with TestClient(
        create_app(config, transport=transport_for(fake), clock=Clock())
    ) as client:
        body = client.get("/healthz").json()
        assert body["credential"] == "app" and body["token_configured"] is True
    with pytest.raises(ConfigError, match="set together"):
        Config.from_env({"GITHUB_APP_CLIENT_ID": "1"})
    with pytest.raises(ConfigError, match="PEM"):
        Config.from_env(
            {
                "GITHUB_APP_CLIENT_ID": "1",
                "GITHUB_APP_INSTALLATION_ID": "2",
                "GITHUB_APP_PRIVATE_KEY": "nope",
            }
        )
    flattened = Config.from_env(
        {
            "GITHUB_APP_CLIENT_ID": "1",
            "GITHUB_APP_INSTALLATION_ID": "2",
            "GITHUB_APP_PRIVATE_KEY": "-----BEGIN X-----\\nabc\\n-----END X-----",
        }
    )
    assert flattened.github_app_private_key == "-----BEGIN X-----\nabc\n-----END X-----"


def test_credentials_can_be_read_from_separate_files(tmp_path: Path) -> None:
    key = tmp_path / "app.pem"
    key.write_text("-----BEGIN X-----\nabc\n-----END X-----\n")
    token = tmp_path / "token"
    token.write_text("ghp_example\n")
    config = Config.from_env(
        {
            "GITHUB_APP_CLIENT_ID": "1",
            "GITHUB_APP_INSTALLATION_ID": "2",
            "GITHUB_APP_PRIVATE_KEY_FILE": str(key),
            "GITHUB_TOKEN_FILE": str(token),
        }
    )
    assert config.github_app_private_key == "-----BEGIN X-----\nabc\n-----END X-----"
    assert config.github_token == "ghp_example"

    with pytest.raises(ConfigError, match="not both"):
        Config.from_env({"GITHUB_TOKEN": "t", "GITHUB_TOKEN_FILE": str(token)})
    with pytest.raises(ConfigError, match="could not be read"):
        Config.from_env({"GITHUB_TOKEN_FILE": str(tmp_path / "missing")})
    (tmp_path / "empty").write_text("\n")
    with pytest.raises(ConfigError, match="empty file"):
        Config.from_env({"GITHUB_TOKEN_FILE": str(tmp_path / "empty")})
    key.write_text("not a key")
    with pytest.raises(ConfigError, match="PEM"):
        Config.from_env(
            {
                "GITHUB_APP_CLIENT_ID": "1",
                "GITHUB_APP_INSTALLATION_ID": "2",
                "GITHUB_APP_PRIVATE_KEY_FILE": str(key),
            }
        )


def test_post_preview_opens_byte_sources_and_preserves_spaces(
    client: TestClient, repo: Repo
) -> None:
    import base64

    from treestamp.document import Document, render_region
    from treestamp.model import Settings, path_value
    from treestamp.session import TreeSession
    from treestamp.sources import TreeRecord, tree_from_records

    root, document = " source\udcff ", " tree\udcfe.md "
    leaf = root + "/file.txt"
    content_id = repo.git("hash-object", "-w", "--stdin", input_bytes=b"file").strip()
    tree = tree_from_records(
        [TreeRecord(leaf, "100644", "blob", content_id)], prefix=root + "/"
    )
    session = TreeSession(tree, Settings(root=root))
    content = render_region(Document(session.printed_tree(), session.settings)).encode()
    document_id = repo.git("hash-object", "-w", "--stdin", input_bytes=content).strip()
    records = b"".join(
        b"100644 "
        + oid.encode()
        + b"\t"
        + path.encode("utf-8", "surrogateescape")
        + b"\0"
        for path, oid in ((leaf, content_id), (document, document_id))
    )
    repo.git("update-index", "-z", "--index-info", input_bytes=records)
    repo.commit("byte document and subtree", stage=False)
    response = client.post(
        "/api/preview",
        json={"url": "o/r", "root": path_value(root), "document": path_value(document)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["root"] == path_value(root) and body["document"] == path_value(document)
    assert body["loaded"] and not body["dirty"]
    assert base64.b64decode(body["state"]["baseline"]) == content
    new = client.post(
        "/api/preview", json={"url": "o/r", "root": path_value(root), "document": ""}
    )
    assert new.status_code == 200 and new.json()["root"] == path_value(root)
    assert new.json()["region"] == body["region"]
    assert not new.json()["loaded"]


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"url": 3},
        {"url": "o/r", "root": None},
        {"url": "o/r", "root": {"git_bytes": "xx"}},
        {"url": "o/r", "document": False},
        {"url": "o/r", "depth": "1"},
    ],
)
def test_post_preview_rejects_invalid_selector_values(
    client: TestClient, body: object
) -> None:
    assert client.post("/api/preview", json=body).status_code == 400


def test_post_preview_shares_limits_and_bounded_json(fake: FakeGitHub) -> None:
    with options_client(
        FakeOptions(), fake, rate_limit_per_minute=4, max_state_bytes=50
    ) as client:
        assert (
            client.post("/api/preview", json={"url": "o/r", "document": ""}).status_code
            == 200
        )
        invalid = client.post(
            "/api/preview",
            content=b"{bad",
            headers={"content-type": "application/json"},
        )
        assert (
            invalid.status_code == 400
            and invalid.json()["error"]["code"] == "invalid_settings"
        )
        assert client.post("/api/preview", json={"url": "x" * 60}).status_code == 413
        assert client.get("/api/preview", params={"url": "o/r"}).status_code == 200
        assert client.post("/api/preview", json={"url": "o/r"}).status_code == 429


@pytest.mark.parametrize("tracked", [False, True])
def test_byte_document_failures_return_safe_diagnostics(
    client: TestClient, repo: Repo, tracked: bool
) -> None:
    name = b"tree\xff.md"
    if tracked:
        oid = repo.git("hash-object", "-w", "--stdin", input_bytes=b"target").strip()
        repo.git(
            "update-index",
            "-z",
            "--index-info",
            input_bytes=b"120000 " + oid.encode() + b"\t" + name + b"\0",
        )
        repo.commit("byte symlink document", stage=False)
    response = client.post(
        "/api/preview", json={"url": "o/r", "document": {"git_bytes": name.hex()}}
    )
    assert response.status_code == (422 if tracked else 404), response.text
    error = response.json()["error"]
    assert error["code"] == ("curation" if tracked else "not_found")
    assert "tree\\udcff.md" in error["message"]
    assert (
        "not a regular file" in error["message"]
        if tracked
        else "does not exist" in error["message"]
    )
