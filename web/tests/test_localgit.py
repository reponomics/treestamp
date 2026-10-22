import base64
import json

from treestamp_web.localgit import FakeGitHub, FakeOptions

from .conftest import Repo


def test_repository_metadata_uses_actual_branch(fake: FakeGitHub, repo: Repo) -> None:
    repo.git("branch", "-m", "release/stable")
    status, _, body = fake.respond("/repos/o/r", {}, "")
    assert status == 200
    assert json.loads(body) == {
        "id": 1,
        "full_name": "o/r",
        "private": False,
        "visibility": "public",
        "default_branch": "release/stable",
    }
    repo.git("checkout", "--detach")
    assert fake.repository.default_branch() is None


def test_fake_routes_cover_shallow_listing_base64_blobs_and_misses(
    fake: FakeGitHub, repo: Repo
) -> None:
    head = repo.git("rev-parse", "HEAD").strip()
    status, headers, body = fake.respond(
        "/repos/o/r/commits/HEAD", {}, "application/vnd.github+json"
    )
    assert status == 200 and json.loads(body)["sha"] == head
    assert headers["x-ratelimit-remaining"] == "59"
    tree = json.loads(body)["commit"]["tree"]["sha"]
    status, _, body = fake.respond(f"/repos/o/r/git/trees/{tree}", {}, "")
    rows = json.loads(body)["tree"]
    assert all("/" not in row["path"] for row in rows) and any(
        row["type"] == "tree" for row in rows
    )
    link = next(row for row in rows if row["path"] == "link")
    status, _, body = fake.respond(f"/repos/o/r/git/blobs/{link['sha']}", {}, "")
    assert base64.b64decode(json.loads(body)["content"]) == b"sub/deep\n\ttarget"
    for path in (
        "/repos/o/r/git/blobs/" + "f" * 40,
        "/repos/o/r/git/trees/" + "f" * 40,
        "/repos/o/r/git/trees/nothex",
        "/repos/o/r/unknown",
        "/elsewhere",
    ):
        assert fake.respond(path, {}, "")[0] == 404
    assert fake.respond("/repos/o/r/git/commits/nothex", {}, "")[0] == 404
    assert fake.respond("/repos/o/r/commits/nope", {}, "")[0] == 422
    fake.options = FakeOptions(rate_limit_after=0)
    status, headers, _ = fake.respond("/rate_limit", {}, "")
    assert status == 403 and headers["x-ratelimit-remaining"] == "0"
