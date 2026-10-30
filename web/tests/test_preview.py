"""The hosted editor opens updated drafts and never tracks advancing HEAD."""

import asyncio
import base64
from dataclasses import replace

import pytest

from treestamp.document import Document, parse_document, render_region
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings
from treestamp.session import TreeSession
from treestamp_web.github import GitHubClient, TooLargeError, UnavailableError
from treestamp_web.links import Repository
from treestamp_web.localgit import FakeGitHub
from treestamp_web.preview import (
    OPEN_NOTICE,
    Envelope,
    Operation,
    Preview,
    PreviewError,
    PreviewRequest,
    PreviewService,
    parse_op_request,
    parse_request,
)

from .conftest import Clock, Repo, make_config, transport_for


def service_for(
    fake: FakeGitHub, clock: Clock | None = None, **config: object
) -> tuple[PreviewService, GitHubClient]:
    clock = clock or Clock()
    client = GitHubClient(
        make_config(**config), transport=transport_for(fake), clock=clock
    )
    return PreviewService(client, make_config(**config), clock), client


def preview(service: PreviewService, **params: str) -> Preview:
    params.setdefault("url", "o/r")
    return asyncio.run(service.preview(parse_request(params)))


def op(
    service: PreviewService,
    previous: Preview,
    kind: str,
    path: object = "",
    text: str = "",
    reveal: bool = False,
) -> Preview:
    return asyncio.run(
        service.apply(
            parse_op_request(
                {
                    "owner": previous.repository.owner,
                    "repo": previous.repository.name,
                    "ref": previous.commit,
                    "root": previous.root,
                    "document": previous.document,
                    "state": previous.state,
                    "reveal": reveal,
                    "op": {"type": kind, "path": path, "text": text},
                }
            )
        )
    )


def stamp(
    repo: Repo,
    *,
    path: str = "README.md",
    root: str = ".",
    expanded: tuple[str, ...] = (),
    hidden: tuple[str, ...] = (),
) -> str:
    # Track the future document before capturing facts; no self-file exception.
    repo.write(path, "# Intro\n")
    repo.git("add", "-A")
    snapshot = capture_snapshot(repo.path / root)
    session = TreeSession(snapshot.tree, Settings(root=root))
    for entry in expanded:
        session.expand(entry)
    for entry in hidden:
        session.hide(entry)
    session.set_annotation("", "repository")
    from treestamp.model import repo_path

    document = Document(
        session.printed_tree(),
        session.settings,
        frozenset(repo_path(p, root) for p in session.saved_hidden()),
    )
    result = "# Intro\n\n" + render_region(document) + "\nOther prose.\n"
    repo.write(path, result)
    repo.commit("document")
    return result


def test_request_has_only_creation_and_document_inputs() -> None:
    assert parse_request({"url": "o/r"}) == PreviewRequest(Repository("o", "r"))
    assert parse_request({"url": "o/r", "document": ""}).document == ""
    assert parse_request({"url": "o/r", "document": "docs/tree.md"}).explicit_document
    request = parse_request(
        {"owner": "o", "repo": "r", "ref": "a" * 40, "root": "src/pkg"}
    )
    assert request.root == "src/pkg" and request.repository.pinned


@pytest.mark.parametrize(
    ("entered", "canonical"),
    [
        ("./sub", "sub"),
        ("./sub/", "sub"),
        ("././sub", "sub"),
        ("sub/.", "sub"),
        ("./", "."),
    ],
)
def test_new_root_normalizes_input_and_preserves_canonical_state(
    fake: FakeGitHub, entered: str, canonical: str
) -> None:
    service, _ = service_for(fake)
    result = preview(service, root=entered, document="")
    assert result.root == canonical
    assert result.state["source"]["root"] == canonical
    assert parse_document(result.region.encode()).settings.root == canonical
    edited = op(service, result, "annotate", "", "note")
    assert edited.root == canonical and "note" in edited.tree


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"owner": "o"},
        {"url": "nope"},
        {"owner": "o", "repo": "r", "ref": "main"},
        {"url": "o/r", "depth": "2"},
        {"url": "o/r", "max_children": "10"},
        {"url": "o/r", "count_mode": "files"},
        {"url": "o/r", "show_counts": "true"},
        {"url": "o/r", "style": "ascii"},
        {"url": "o/r", "hide_root_files": "false"},
        {"url": "o/r", "root": ".."},
        {"url": "o/r", "root": "./../sub"},
        {"url": "o/r", "root": "sub/../sub"},
        {"url": "o/r", "root": "/sub"},
        {"url": "o/r", "document": "../tree.md"},
    ],
)
def test_invalid_requests(params: dict[str, str]) -> None:
    with pytest.raises(PreviewError) as error:
        parse_request(params)
    assert error.value.status == 400


def test_new_uses_depth_one_all_children_and_full_counts(fake: FakeGitHub) -> None:
    service, _ = service_for(fake)
    result = preview(service)
    assert result.root_children == 6 and result.entries == 10
    assert "top.txt" in result.tree and "sub/ (2 files, 1 folder)" in result.tree
    assert "other.txt" not in result.tree and result.loaded is False and result.dirty
    assert result.state["curation"]["hidden"] == []
    assert result.notice is None and result.warnings == []
    assert result.permalink(None) == f"/o/r@{result.commit}?root=."
    assert result.permalink("https://x.test/").startswith("https://x.test/o/r@")
    assert result.to_dict(None)["repository"]["default_branch"] == "main"


def test_branch_link_notice(fake: FakeGitHub) -> None:
    service, _ = service_for(fake)
    result = preview(service, url="https://github.com/o/r/blob/main/README.md")
    assert result.repository.ref == "HEAD" and "ignored" in result.warnings[0]


def test_open_updates_before_editing_and_keeps_baseline(
    fake: FakeGitHub, repo: Repo
) -> None:
    original = stamp(repo, expanded=("sub",), hidden=("top.txt",))
    service, _ = service_for(fake)
    unchanged = preview(service)
    assert unchanged.loaded and not unchanged.dirty and unchanged.notice is None
    repo.write("sub/new.txt")
    (repo.path / "sub/other.txt").unlink()
    repo.commit("growth and deletion")
    updated = preview(service)
    assert updated.dirty and updated.notice == OPEN_NOTICE
    assert "new.txt" in updated.tree and "other.txt" not in updated.tree
    assert "top.txt" not in updated.tree and "repository" in updated.tree
    assert (repo.path / "README.md").read_text() == original
    assert updated.state["curation"]["hidden"] == ["top.txt"]
    noted = op(service, updated, "annotate", "sub/new.txt", "new annotation")
    assert noted.state["baseline"] == updated.state["baseline"]
    assert noted.notice is None and noted.dirty
    assert noted.state["generation"] == updated.state["generation"]
    assert noted.state["revision"] == updated.state["revision"] + 1


def test_special_row_identity_survives_hosted_annotation_and_visibility_edits(
    fake: FakeGitHub, repo: Repo
) -> None:
    repo.write("special/x")
    repo.write("special/x  # y")
    stamp(repo, root="special")
    service, _ = service_for(fake)
    loaded = preview(service)
    assert loaded.loaded and not loaded.dirty
    # Both rows now print the same name/annotation text, but their row metadata
    # preserves the two distinct filenames through each API round trip.
    annotated = op(service, loaded, "annotate", "x", "y")
    parsed = parse_document(annotated.region.encode())
    assert {node.path: node.annotation for node in parsed.tree.walk()} == {
        "x": "y",
        "x  # y": "",
    }
    hidden = op(service, annotated, "hide", "x  # y")
    assert "special_paths" not in hidden.region
    assert parse_document(hidden.region.encode()).hidden == frozenset(
        {"special/x  # y"}
    )
    restored = op(service, hidden, "unhide", "x  # y")
    assert restored.region == annotated.region


def test_root_is_repo_relative_and_absent_subtree_is_valid(
    fake: FakeGitHub, repo: Repo
) -> None:
    stamp(repo, path="docs/tree.md", root="sub")
    service, _ = service_for(fake)
    result = preview(service, document="docs/tree.md")
    assert result.root == "sub" and 'root = "sub"' in result.region
    assert 'root = "../sub"' not in result.region
    assert result.permalink(None).endswith("root=sub&document=docs%2Ftree.md")
    hidden = op(service, result, "hide", "deep")
    assert 'hidden = ["sub/deep"]' in hidden.region
    repo.git("rm", "-r", "sub")
    repo.commit("remove subtree")
    empty = preview(service, document="docs/tree.md")
    assert empty.root_children == 0 and empty.dirty
    repo.write("sub", "now a file")
    repo.commit("replace subtree with leaf")
    with pytest.raises(PreviewError, match="not a directory"):
        preview(service, document="docs/tree.md")


def test_default_missing_document_and_explicit_document_intent(
    fake: FakeGitHub, repo: Repo
) -> None:
    service, _ = service_for(fake)
    assert not preview(service).loaded
    with pytest.raises(PreviewError, match="does not exist"):
        preview(service, document="README.md")
    repo.write("README.md", "plain text\n")
    repo.commit("plain README")
    assert not preview(service).loaded
    with pytest.raises(PreviewError):
        preview(service, document="README.md")
    repo.write("README.md", "<!-- treestamp:start -->\n<!-- treestamp:end -->\n")
    repo.commit("empty region")
    with pytest.raises(PreviewError):
        preview(service)
    assert not preview(service, document="").loaded


def test_bad_and_nonregular_documents_fail(fake: FakeGitHub, repo: Repo) -> None:
    service, _ = service_for(fake)
    with pytest.raises(PreviewError, match="not a regular"):
        preview(service, document="link")
    repo.write(
        "README.md",
        "<!-- treestamp:start -->\n<!-- treestamp:start -->\n<!-- treestamp:end -->\n",
    )
    repo.commit()
    with pytest.raises(PreviewError, match="duplicate or nested"):
        preview(service)


def test_edit_and_state_restore_never_follow_head(fake: FakeGitHub, repo: Repo) -> None:
    clock = Clock()
    service, client = service_for(fake, clock)
    first = preview(service)
    repo.write("new.txt")
    repo.write("sub/another.txt")
    repo.commit("advance HEAD")
    clock.now += 100
    expanded = op(service, first, "expand", "sub")
    assert expanded.commit == first.commit and "another.txt" not in expanded.tree
    calls = client.calls
    restored = op(service, expanded, "restore")
    assert restored.state == expanded.state and restored.region == expanded.region
    assert client.calls == calls
    # A different service cannot refetch a historical snapshot after cache loss.
    other, other_client = service_for(fake, clock)
    with pytest.raises(PreviewError, match="snapshot is unavailable"):
        op(other, expanded, "restore")
    assert other_client.calls == 0
    fresh = preview(service)
    assert fresh.commit != first.commit and "new.txt" in fresh.tree
    assert fresh.state["generation"] != first.state["generation"]
    assert fresh.state["curation"]["expanded"] == []


def test_hiding_counts_and_collapse_projection(fake: FakeGitHub) -> None:
    service, _ = service_for(fake)
    result = op(service, preview(service), "expand", "sub")
    result = op(service, result, "hide", "sub/other.txt")
    result = op(service, result, "annotate", "sub", "sources")
    result = op(service, result, "collapse", "sub")
    assert "sub/ (2 files, 1 folder)  # sources" in result.tree
    parsed = parse_document(result.region.encode())
    assert parsed.hidden == frozenset()
    result = op(service, result, "expand", "sub")
    assert "other.txt" not in result.tree
    result = op(service, result, "unhide", "sub/other.txt")
    assert "other.txt" in result.tree
    result = op(service, result, "hide", "top.txt")
    revealed = op(service, result, "restore", reveal=True)
    assert next(row for row in revealed.rows if row["path"] == "top.txt")["hidden"]
    result = op(service, result, "unhide_all")
    assert all(not row["hidden"] for row in result.rows)
    assert result.state["curation"]["hidden"] == []


def test_show_counts_and_style_are_session_only(fake: FakeGitHub) -> None:
    service, _ = service_for(fake)
    first = preview(service)
    first.state["curation"]["settings"].update(show_counts=False, style="ascii")
    result = op(service, first, "present")
    assert result.state["revision"] == first.state["revision"] + 1
    assert "|--" in result.tree and "files)" not in result.tree
    assert "show_counts" not in result.region and "style =" not in result.region


@pytest.mark.parametrize("style", ["unicode", "ascii", "list"])
def test_attribution_is_opt_in_and_survives_loading_and_editing(
    fake: FakeGitHub, repo: Repo, style: str
) -> None:
    service, _ = service_for(fake)
    original = preview(service)
    assert original.state["curation"]["settings"]["attribution"] is False
    assert "Maintained with" not in original.region
    original.state["curation"]["settings"].update(attribution=True, style=style)
    enabled = op(service, original, "present")
    trailer = "Maintained with [treestamp](https://github.com/reponomics/treestamp)"
    assert enabled.region.endswith(f"\n\n{trailer}\n<!-- treestamp:end -->\n")
    assert parse_document(enabled.region.encode()).settings.attribution is True
    repo.write("README.md", enabled.region)
    repo.commit("document with attribution")
    loaded = preview(service, document="README.md")
    assert loaded.state["curation"]["settings"]["attribution"] is True
    edited = op(service, loaded, "annotate", "", "repository note")
    assert trailer in edited.region
    edited.state["curation"]["settings"]["attribution"] = False
    disabled = op(service, edited, "present")
    assert trailer not in disabled.region
    assert parse_document(disabled.region.encode()).settings.attribution is False


def test_byte_identity_survives_rows_state_and_operations(
    fake: FakeGitHub, repo: Repo
) -> None:
    oid = repo.git("hash-object", "-w", "--stdin", input_bytes=b"raw").strip()
    repo.git(
        "update-index",
        "-z",
        "--index-info",
        input_bytes=b"100644 " + oid.encode() + b"\traw\xff\0",
    )
    repo.commit("byte name", stage=False)
    service, _ = service_for(fake)
    result = preview(service)
    row = next(row for row in result.rows if isinstance(row["path"], dict))
    assert (
        row["path"] == {"git_bytes": b"raw\xff".hex()}
        and row["key"] == b"raw\xff".hex()
    )
    annotated = op(service, result, "annotate", row["path"], "kept")
    assert {"path": row["path"], "text": "kept"} in annotated.state["curation"][
        "annotations"
    ]
    hidden = op(service, annotated, "hide", row["path"])
    assert hidden.state["curation"]["hidden"] == [row["path"]]
    assert op(service, hidden, "unhide", row["path"]).region == annotated.region


def test_required_symlink_facts_cannot_be_null(
    fake: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _ = service_for(fake, symlink_fetch_limit=1)
    with pytest.raises(PreviewError, match="service limit"):
        preview(service)

    async def unavailable(
        self: GitHubClient, owner: str, repo: str, oid: str, **kwargs: object
    ) -> bytes:
        raise UnavailableError("blob unavailable")

    monkeypatch.setattr(GitHubClient, "blob", unavailable)
    service, _ = service_for(fake)
    with pytest.raises(UnavailableError, match="blob unavailable"):
        preview(service)


def test_document_cap_and_source_errors(
    fake: FakeGitHub, repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    stamp(repo)

    async def too_large(
        self: GitHubClient, owner: str, repo: str, oid: str, **kwargs: object
    ) -> bytes:
        raise TooLargeError("too large")

    monkeypatch.setattr(GitHubClient, "blob", too_large)
    service, _ = service_for(fake)
    with pytest.raises(PreviewError, match="larger than the service reads"):
        preview(service)


def test_metadata_failure_prevents_acquisition(
    fake: FakeGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(self: GitHubClient, owner: str, repo: str) -> str:
        raise UnavailableError("metadata unavailable")

    monkeypatch.setattr(GitHubClient, "public_repository", unavailable)
    service, client = service_for(fake)
    with pytest.raises(UnavailableError, match="metadata unavailable"):
        preview(service)
    assert client.calls == 0 and service.stats()["trees"] == 0


def test_noncanonical_and_crlf_baselines_survive_restore(
    fake: FakeGitHub, repo: Repo
) -> None:
    stamp(repo)
    path = repo.path / "README.md"
    data = path.read_bytes().replace(b"\n", b"\r\n")
    path.write_bytes(data)
    repo.commit("CRLF")
    service, _ = service_for(fake)
    result = preview(service)
    assert not result.dirty
    assert b"\r\n" in base64.b64decode(result.state["baseline"])
    assert not op(service, result, "restore").dirty
    path.write_bytes(data.replace(b"```sh\r\n", b"```text\r\n"))
    repo.commit("cosmetic drift")
    result = preview(service)
    assert result.dirty and result.notice == OPEN_NOTICE
    assert op(service, result, "restore").dirty


@pytest.mark.parametrize("eol", [b"\n", b"\r\n"])
@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"])
def test_boundary_line_endings_do_not_create_unwritten_changes(
    fake: FakeGitHub, repo: Repo, eol: bytes, ending: bytes
) -> None:
    stamp(repo)
    path = repo.path / "README.md"
    before_end = path.read_bytes().split(b"<!-- treestamp:end -->")[0]
    original = before_end.replace(b"\n", eol) + b"<!-- treestamp:end -->" + ending
    path.write_bytes(original)
    repo.commit("boundary line endings")
    service, _ = service_for(fake)
    result = preview(service)
    assert result.loaded and not result.dirty and result.notice is None
    restored = op(service, result, "restore")
    assert not restored.dirty
    changed = op(service, restored, "annotate", "", "edited")
    assert changed.dirty
    reverted = op(service, changed, "annotate", "", "repository")
    assert not reverted.dirty
    assert path.read_bytes() == original


@pytest.mark.parametrize(
    "marker", ["<!-- treestamp:start -->", "<!-- treestamp:end -->"]
)
def test_open_rejects_indented_boundaries(
    fake: FakeGitHub, repo: Repo, marker: str
) -> None:
    original = stamp(repo).replace(marker, "  " + marker)
    repo.write("README.md", original)
    repo.commit("invalid boundary")
    service, _ = service_for(fake)
    with pytest.raises(PreviewError, match="boundary markers must not be indented"):
        preview(service)
    assert (repo.path / "README.md").read_text() == original


@pytest.mark.parametrize(
    "operation",
    [
        None,
        {},
        {"type": "carry"},
        {"type": "maintain"},
        {"type": "hide", "path": 3},
        {"type": "annotate", "text": 5},
        {"type": "restore", "extra": True},
    ],
)
def test_invalid_operations(operation: object) -> None:
    with pytest.raises(PreviewError):
        Operation.from_dict(operation)


def test_invalid_state_and_request_validation(fake: FakeGitHub) -> None:
    service, _ = service_for(fake)
    first = preview(service)
    body = {
        "owner": "o",
        "repo": "r",
        "ref": first.commit,
        "root": ".",
        "document": first.document,
        "state": first.state,
        "op": {"type": "restore"},
    }
    for bad in (
        [],
        {},
        {**body, "ref": "HEAD"},
        {**body, "ref": "bad ref"},
        {**body, "extra": True},
        {**body, "reveal": "yes"},
        {**body, "root": "sub"},
        {**body, "state": {}},
    ):
        with pytest.raises(PreviewError):
            parse_op_request(bad)
    for change in (
        {"version": 2},
        {"revision": -1},
        {"generation": ""},
        {"baseline": "not-base64"},
        {"baseline": 5},
        {"source": []},
        {"curation": {"old": True}},
    ):
        with pytest.raises(PreviewError):
            Envelope.from_dict({**first.state, **change})
    with pytest.raises(PreviewError, match="not a tracked"):
        op(service, first, "annotate", "gone", "text")
    state = dict(first.state)
    state["curation"] = {**state["curation"], "expanded": ["gone"]}
    with pytest.raises(PreviewError, match="not a tracked"):
        op(service, replace(first, state=state), "restore")


def test_byte_root_permalink_restores_exact_snapshot_state(
    fake: FakeGitHub, repo: Repo
) -> None:
    import json

    oid = repo.git("hash-object", "-w", "--stdin", input_bytes=b"raw").strip()
    repo.git(
        "update-index",
        "-z",
        "--index-info",
        input_bytes=b"100644 " + oid.encode() + b"\traw\xff/file\0",
    )
    repo.commit("byte subtree", stage=False)
    service, _ = service_for(fake)
    result = asyncio.run(
        service.preview(
            PreviewRequest(Repository("o", "r"), root="raw\udcff", document="")
        )
    )
    permalink = result.permalink(None)
    fragment = permalink.split("#s=", 1)[1]
    state = json.loads(base64.urlsafe_b64decode(fragment + "=" * (-len(fragment) % 4)))
    assert state["source"]["root"] == {"git_bytes": b"raw\xff".hex()}
    assert "%EF%BF%BD" not in permalink
    restored = asyncio.run(
        service.apply(
            parse_op_request(
                {
                    "owner": "o",
                    "repo": "r",
                    "ref": result.commit,
                    "root": state["source"]["root"],
                    "document": "",
                    "state": state,
                    "op": {"type": "restore"},
                }
            )
        )
    )
    assert restored.region == result.region
