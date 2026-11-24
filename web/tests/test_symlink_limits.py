"""Symlink budgets charge expanded references before constructing source trees."""

import asyncio
from dataclasses import replace

import pytest

from treestamp.document import Document, parse_document, render_region
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings
from treestamp_web import preview as preview_module
from treestamp_web.config import Config, ConfigError
from treestamp_web.github import GitHubClient
from treestamp_web.links import Repository
from treestamp_web.localgit import FakeGitHub, LocalRepository

from .conftest import Repo
from .test_placement import placed
from .test_preview import op, preview, service_for


def repository(
    repo: Repo, targets: dict[str, bytes], *, document: bool = False
) -> FakeGitHub:
    """Tiny Git objects allow byte targets without platform symlink restrictions."""
    repo.write("README.md", "# Fixture\n")
    repo.git("add", "README.md")
    for path, target in targets.items():
        oid = repo.git("hash-object", "-w", "--stdin", input_bytes=target).strip()
        repo.git("update-index", "--add", "--cacheinfo", f"120000,{oid},{path}")
    if document:
        tree = capture_snapshot(repo.path).tree
        repo.write("README.md", render_region(Document(tree, Settings())))
        repo.git("add", "README.md")
    repo.commit(stage=False)
    return FakeGitHub(LocalRepository(repo.path))


def forbid_tree_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected(*args: object, **kwargs: object) -> None:
        pytest.fail("over-budget symlinks reached tree construction")

    monkeypatch.setattr(preview_module, "tree_from_records", unexpected)


@pytest.mark.parametrize("target", [b"target", "café".encode(), b"raw\xff\n\t"])
def test_shared_targets_at_exact_byte_budget_are_fetched_once_and_preserved(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, target: bytes
) -> None:
    targets = {"first": target, "second": target}
    service, _ = service_for(
        repository(repo, targets),
        symlink_fetch_limit=1,
        symlink_target_max_bytes=len(target),
        symlink_expanded_max_bytes=sum(map(len, targets.values())),
    )
    calls: list[tuple[str, int | None]] = []
    original = GitHubClient.blob

    async def counted(
        self: GitHubClient, owner: str, name: str, oid: str, *, cap: int | None = None
    ) -> bytes:
        calls.append((oid, cap))
        return await original(self, owner, name, oid, cap=cap)

    monkeypatch.setattr(GitHubClient, "blob", counted)
    opened = preview(service, document="")
    restored = op(service, opened, "restore")

    assert len(calls) == 1 and calls[0][1] == len(target)
    assert restored.region == opened.region
    actual = {
        node.path: node.target
        for node in parse_document(opened.region.encode()).tree.walk()
        if node.target is not None
    }
    assert actual == {
        path: value.decode("utf-8", "surrogateescape")
        for path, value in targets.items()
    }


@pytest.mark.parametrize(
    "targets",
    [
        {"first": b"target", "second": b"target"},
        {"first": b"one", "second": b"another"},
        {"first": "café".encode(), "second": b"raw\xff"},
    ],
)
def test_aggregate_budget_rejects_before_decoding_or_rendering(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, targets: dict[str, bytes]
) -> None:
    service, _ = service_for(
        repository(repo, targets),
        symlink_expanded_max_bytes=sum(map(len, targets.values())) - 1,
    )
    forbid_tree_construction(monkeypatch)

    with pytest.raises(preview_module.PreviewError) as error:
        preview(service, document="")

    assert (error.value.status, error.value.code) == (422, "source_unavailable")
    assert service.stats()["trees"] == 0


def test_individual_streamed_target_limit_rejects_before_tree_construction(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = b"target"
    service, _ = service_for(
        repository(repo, {"link": target}), symlink_target_max_bytes=len(target) - 1
    )
    forbid_tree_construction(monkeypatch)

    with pytest.raises(preview_module.PreviewError) as error:
        preview(service, document="")

    assert (error.value.status, error.value.code) == (422, "source_unavailable")


def test_only_selected_subtree_references_consume_the_budget(repo: Repo) -> None:
    target = b"target"
    service, _ = service_for(
        repository(
            repo,
            {"selected/link": target, "selected-other/link": target, "outside": target},
        ),
        symlink_target_max_bytes=len(target),
        symlink_expanded_max_bytes=len(target),
    )

    opened = preview(service, root="selected", document="")

    assert opened.root == "selected"
    assert (
        parse_document(opened.region.encode()).tree.children[0].target
        == target.decode()
    )


@pytest.mark.parametrize("operation", ["restore", "place", "preview"])
@pytest.mark.parametrize(
    "limit", ["symlink_target_max_bytes", "symlink_expanded_max_bytes"]
)
def test_cached_source_cannot_bypass_current_byte_limits(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, operation: str, limit: str
) -> None:
    target = b"target"
    service, client = service_for(
        repository(repo, {"first": target, "second": target}, document=True)
    )
    opened = preview(service)
    calls = client.calls
    bound = len(target) if limit == "symlink_target_max_bytes" else 2 * len(target)
    monkeypatch.setattr(
        service, "_config", replace(service._config, **{limit: bound - 1})
    )
    forbid_tree_construction(monkeypatch)

    async def unexpected_blob(*args: object, **kwargs: object) -> bytes:
        pytest.fail("cached source fetched a blob again")

    monkeypatch.setattr(GitHubClient, "blob", unexpected_blob)

    with pytest.raises(preview_module.PreviewError) as error:
        if operation == "place":
            placed(service, opened)
        elif operation == "preview":
            preview(service, ref=opened.commit)
        else:
            op(service, opened, operation)

    assert (error.value.status, error.value.code) == (422, "source_unavailable")
    if operation != "preview":
        assert client.calls == calls


def test_cached_document_blob_is_checked_again_as_a_symlink_target(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = b"shared document bytes"
    fake = repository(repo, {"link": target})
    service, client = service_for(fake, symlink_target_max_bytes=len(target) - 1)
    source = Repository("o", "r")
    snapshot, acquired = asyncio.run(service._preview_snapshot(source))
    oid = next(record.object_id for record in snapshot.records if record.path == "link")
    assert (
        asyncio.run(
            service._blob(
                source, snapshot, oid, acquired, cap=preview_module.DOCUMENT_CAP
            )
        )
        == target
    )
    calls = client.calls
    forbid_tree_construction(monkeypatch)

    with pytest.raises(preview_module.PreviewError) as error:
        asyncio.run(service._target(source, snapshot, ".", False))

    assert (error.value.status, error.value.code) == (422, "source_unavailable")
    assert client.calls == calls


def test_zero_byte_budgets_allow_a_tree_without_symlinks(repo: Repo) -> None:
    service, _ = service_for(
        repository(repo, {}), symlink_target_max_bytes=0, symlink_expanded_max_bytes=0
    )
    assert preview(service, document="").rows


@pytest.mark.parametrize(
    "name", ["SYMLINK_TARGET_MAX_BYTES", "SYMLINK_EXPANDED_MAX_BYTES"]
)
def test_byte_limit_configuration_is_nonnegative(name: str) -> None:
    for value in (0, 1, 123):
        assert getattr(Config.from_env({name: str(value)}), name.lower()) == value
    with pytest.raises(ConfigError):
        Config.from_env({name: "-1"})
