"""Real Git index snapshots, independent of the TUI."""

from pathlib import Path

import pytest

from treestamp import gitio, sources
from treestamp.errors import GitEnvironmentError, MarkerError
from treestamp.gitio import capture_snapshot, checked_path
from treestamp.model import KIND_FILE, KIND_GITLINK, KIND_SYMLINK

from .conftest import Repo


def paths(snapshot: gitio.Snapshot) -> dict[str, str]:
    return {node.path: node.kind for node in snapshot.tree.walk()}


def baseline(repo: Repo) -> str:
    repo.write("old/file.txt", "unique source content\n")
    repo.add(".")
    repo.commit()
    return repo.git("rev-parse", "HEAD").strip()


def test_index_is_truth_even_for_missing_and_ignored_tracked_files(repo: Repo) -> None:
    repo.write("tracked", "x")
    repo.write(".gitignore", "tracked\nignored\n")
    repo.add(".gitignore")
    repo.git("add", "-f", "tracked")
    (repo.path / "tracked").unlink()
    repo.write("ignored")
    repo.write("untracked")
    assert paths(capture_snapshot(repo.path)) == {
        ".gitignore": KIND_FILE,
        "tracked": KIND_FILE,
    }


def test_index_snapshot_includes_staged_changes_only(repo: Repo) -> None:
    baseline(repo)
    repo.write("staged")
    repo.add("staged")
    repo.write("unstaged")
    assert "staged" in paths(capture_snapshot(repo.path))
    assert "unstaged" not in paths(capture_snapshot(repo.path))


def test_index_snapshot_does_not_need_commit(repo: Repo) -> None:
    assert capture_snapshot(repo.path).tree.children == ()


def test_snapshot_remains_fixed_after_index_changes(repo: Repo) -> None:
    baseline(repo)
    repo.write("first")
    repo.add("first")
    snapshot = capture_snapshot(repo.path)
    repo.write("second")
    repo.add("second")
    assert "first" in paths(snapshot) and "second" not in paths(snapshot)


def test_symlink_target_read_from_blob_not_filesystem(repo: Repo) -> None:
    link = repo.path / "link"
    link.symlink_to("original\n\ttarget")
    repo.add("link")
    link.unlink()
    link.symlink_to("different")
    node = capture_snapshot(repo.path).tree.children[0]
    assert node.kind == KIND_SYMLINK
    assert node.target == "original\n\ttarget"


def test_gitlinks_are_leaves(repo: Repo) -> None:
    commit = baseline(repo)
    repo.git("update-index", "--add", "--cacheinfo", f"160000,{commit},module")
    result = paths(capture_snapshot(repo.path))
    assert result["module"] == KIND_GITLINK
    assert not any(path.startswith("module/") for path in result)


def test_unusual_paths_survive_nul_protocol(repo: Repo) -> None:
    path = "dir/line\nwith\ttab and ünicode\\name"
    blob = repo.blob(b"distinct content\n")
    subtree = repo.tree([("100644", "blob", blob, path.split("/", 1)[1])])
    tree = repo.tree([("040000", "tree", subtree, "dir")])
    # These object names cannot enter a Windows index or working tree.
    entries = gitio._entries(repo.path, tree, "")
    assert {entry.path: entry.kind for entry in entries.values()} == {path: KIND_FILE}


def test_scope_root_may_be_missing_from_worktree(repo: Repo) -> None:
    baseline(repo)
    (repo.path / "old/file.txt").unlink()
    (repo.path / "old").rmdir()
    snapshot = capture_snapshot(repo.path / "old")
    assert snapshot.root == repo.path / "old"
    assert paths(snapshot) == {"file.txt": KIND_FILE}


def test_unmerged_index_fails(repo: Repo) -> None:
    baseline(repo)
    repo.git("checkout", "-qb", "other")
    repo.write("old/file.txt", "other\n")
    repo.add(".")
    repo.commit()
    repo.git("checkout", "-q", "main")
    repo.write("old/file.txt", "main\n")
    repo.add(".")
    repo.commit()
    import subprocess

    subprocess.run(
        ["git", "merge", "other"], cwd=repo.path, capture_output=True, check=False
    )
    with pytest.raises(GitEnvironmentError, match="write-tree"):
        capture_snapshot(repo.path)


def test_invalid_scope_fails(repo: Repo) -> None:
    baseline(repo)
    assert capture_snapshot(repo.path / "absent").tree.children == ()
    with pytest.raises(MarkerError, match="tracked leaf"):
        capture_snapshot(repo.path / "old/file.txt")


def test_symlink_root_rejected(repo: Repo) -> None:
    baseline(repo)
    (repo.path / "alias").symlink_to("old", target_is_directory=True)
    with pytest.raises(MarkerError, match="symbolic link"):
        checked_path(repo.path / "alias/file.txt")


def test_collection_limits_fail_explicitly(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline(repo)
    monkeypatch.setattr(sources, "MAX_ENTRIES", 0)
    with pytest.raises(GitEnvironmentError, match="entry limit"):
        capture_snapshot(repo.path)
    monkeypatch.setattr(gitio, "MAX_OUTPUT_BYTES", 1)
    with pytest.raises(GitEnvironmentError, match="byte limit"):
        capture_snapshot(repo.path)


def test_missing_git_and_nonrepo_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(GitEnvironmentError):
        capture_snapshot(tmp_path)
    monkeypatch.setenv("PATH", "")
    with pytest.raises(GitEnvironmentError, match="not on PATH"):
        capture_snapshot(tmp_path)


def test_disappeared_selected_root_has_empty_facts(repo: Repo) -> None:
    baseline(repo)
    repo.git("rm", "-r", "old")
    assert capture_snapshot(repo.path / "old").tree.children == ()


def test_selected_root_cannot_be_a_tracked_leaf(repo: Repo) -> None:
    repo.write("leaf")
    repo.add("leaf")
    with pytest.raises(MarkerError, match="tracked leaf"):
        capture_snapshot(repo.path / "leaf")


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"100644 blob id name",
        b"100644\tname",
        b"999999 blob id\tname",
        b"040000 tree id\tdir",
    ],
)
def test_malformed_tree_records_fail_explicitly(raw: bytes) -> None:
    with pytest.raises(GitEnvironmentError, match="invalid Git tree record"):
        gitio._tree_record(raw)


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"missing", "cannot read symlink blob"),
        (b"id missing\n", "cannot read symlink blob"),
        (b"id tree 1\nx\n", "cannot read symlink blob"),
        (b"id blob invalid\nx\n", "invalid symlink blob size"),
        (b"id blob -1\n", "incomplete symlink blob"),
        (b"id blob 3\nx\n", "incomplete symlink blob"),
        (b"id blob 1\nxy", "incomplete symlink blob"),
    ],
)
def test_invalid_symlink_batch_output_fails_with_path(
    raw: bytes, message: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gitio, "_git", lambda *args, **kwargs: raw)
    with pytest.raises(GitEnvironmentError, match=f"{message}: link"):
        gitio._symlink_targets(tmp_path, {"link": "id"})


def test_symlink_batch_uses_lengths_for_empty_and_multiline_targets(
    repo: Repo,
) -> None:
    targets = {"empty": b"", "multiline": b"one\nline\n\xff", "repeat": b""}
    links = {path: repo.blob(target) for path, target in targets.items()}
    assert gitio._symlink_targets(repo.path, links) == {
        path: target.decode("utf-8", "surrogateescape")
        for path, target in targets.items()
    }


def test_explicit_repository_rejects_outside_snapshot_root(repo: Repo) -> None:
    with pytest.raises(GitEnvironmentError, match="root is outside repository"):
        capture_snapshot(repo.path.parent, repository=repo.path)


@pytest.mark.parametrize("failure", ["oserror", "timeout"])
def test_git_process_failure_preserves_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    import subprocess

    error = (
        OSError("cannot start process")
        if failure == "oserror"
        else subprocess.TimeoutExpired("git", 60)
    )

    def fail(*args: object, **kwargs: object) -> None:
        raise error

    monkeypatch.setattr(gitio.subprocess, "run", fail)
    with pytest.raises(GitEnvironmentError, match="cannot run git rev-parse") as exc:
        gitio.repo_root(tmp_path)
    assert exc.value.__cause__ is error


def test_path_inspection_failure_preserves_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from treestamp.errors import ExecutionError

    original = Path.lstat
    error = PermissionError("inspection denied")

    def fail_selected(path: Path, *args: object, **kwargs: object):
        if path == tmp_path:
            raise error
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fail_selected)
    with pytest.raises(ExecutionError, match="cannot inspect") as exc:
        checked_path(tmp_path)
    assert exc.value.__cause__ is error
