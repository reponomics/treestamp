"""Real Git snapshots and endpoint comparisons, independent of the TUI."""

from pathlib import Path

import pytest

from treestamp import gitio, sources
from treestamp.errors import GitEnvironmentError, MarkerError
from treestamp.gitio import capture_snapshot, changes, checked_path
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


def test_ref_snapshot_ignores_index_and_worktree_changes(repo: Repo) -> None:
    baseline(repo)
    repo.write("staged")
    repo.add("staged")
    repo.write("unstaged")
    assert "staged" not in paths(capture_snapshot(repo.path, "HEAD"))
    assert "staged" in paths(capture_snapshot(repo.path))
    assert "unstaged" not in paths(capture_snapshot(repo.path))


def test_index_snapshot_does_not_need_commit(repo: Repo) -> None:
    assert capture_snapshot(repo.path).tree.children == ()
    with pytest.raises(GitEnvironmentError):
        capture_snapshot(repo.path, "HEAD")


def test_snapshot_remains_fixed_after_index_changes(repo: Repo) -> None:
    baseline(repo)
    repo.write("first")
    repo.add("first")
    snapshot = capture_snapshot(repo.path)
    repo.write("second")
    repo.add("second")
    assert "first" in paths(snapshot) and "second" not in paths(snapshot)


def test_empty_comparison_is_exhaustive(repo: Repo) -> None:
    baseline(repo)
    result = changes(capture_snapshot(repo.path), "HEAD")
    assert result.moves == {}


def test_staged_rename_transfers_only_leaf_and_adds_destination(repo: Repo) -> None:
    before = baseline(repo)
    repo.git("mv", "old", "renamed")
    result = changes(capture_snapshot(repo.path), before)
    assert result.moves == {"old/file.txt": "renamed/file.txt"}


def test_copy_is_addition_not_move(repo: Repo) -> None:
    before = baseline(repo)
    repo.write("copy", (repo.path / "old/file.txt").read_text(encoding="utf-8"))
    repo.add("copy")
    result = changes(capture_snapshot(repo.path), before)
    assert result.moves == {}


def test_file_directory_and_symlink_replacements_are_additions(repo: Repo) -> None:
    repo.write("becomes_dir", "old directory-path file\n")
    repo.write("becomes_file/child", "old child file\n")
    repo.write("becomes_link", "old regular file\n")
    repo.add(".")
    repo.commit()
    repo.git("rm", "-r", "becomes_dir", "becomes_file", "becomes_link")
    repo.write("becomes_dir/child", "unrelated child content\n")
    repo.write("becomes_file", "unrelated replacement content\n")
    (repo.path / "becomes_link").symlink_to("becomes_file")
    repo.add(".")
    result = changes(capture_snapshot(repo.path), "HEAD")
    assert result.moves == {}


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
    original = "old/line\nwith\ttab and ünicode\\name"
    destination = "new/line\nwith\ttab and ünicode\\name"
    blob = repo.blob(b"distinct content\n")
    subtree = repo.tree([("100644", "blob", blob, original.split("/", 1)[1])])
    before = repo.tree([("040000", "tree", subtree, "old")])
    after = repo.tree([("040000", "tree", subtree, "new")])
    result = changes(capture_snapshot(repo.path, after), before)
    assert result.moves == {original: destination}


def test_scope_root_may_be_missing_from_worktree(repo: Repo) -> None:
    baseline(repo)
    (repo.path / "old/file.txt").unlink()
    (repo.path / "old").rmdir()
    snapshot = capture_snapshot(repo.path / "old")
    assert snapshot.root == repo.path / "old"
    assert paths(snapshot) == {"file.txt": KIND_FILE}


def test_scope_comparison_can_precede_root_creation(repo: Repo) -> None:
    before = baseline(repo)
    repo.write("new/sub/file")
    repo.add(".")
    snapshot = capture_snapshot(repo.path / "new")
    assert changes(snapshot, before).moves == {}


def test_scope_excludes_cross_boundary_rename_transfer(repo: Repo) -> None:
    baseline(repo)
    repo.write("inside/keep")
    repo.add(".")
    repo.commit()
    repo.git("mv", "old/file.txt", "inside/file.txt")
    result = changes(capture_snapshot(repo.path / "inside"), "HEAD")
    assert result.moves == {}


@pytest.mark.parametrize("ref", ["missing-ref", "--help", "HEAD:old/file.txt"])
def test_invalid_target_refs_fail(repo: Repo, ref: str) -> None:
    baseline(repo)
    with pytest.raises(GitEnvironmentError):
        capture_snapshot(repo.path, ref)


def test_missing_comparison_ref_fails(repo: Repo) -> None:
    baseline(repo)
    with pytest.raises(GitEnvironmentError):
        changes(capture_snapshot(repo.path), "missing-ref")


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
    assert paths(capture_snapshot(repo.path, "HEAD"))


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


def test_move_chains_are_not_supported() -> None:
    assert (
        gitio._supported_moves(
            [("a", "b"), ("b", "c")],
            {"a": KIND_FILE, "b": KIND_FILE},
            {"b": KIND_FILE, "c": KIND_FILE},
            "",
        )
        == {}
    )


def test_disappeared_selected_root_has_empty_facts(repo: Repo) -> None:
    baseline(repo)
    repo.git("rm", "-r", "old")
    assert capture_snapshot(repo.path / "old").tree.children == ()


def test_selected_root_cannot_be_a_tracked_leaf(repo: Repo) -> None:
    repo.write("leaf")
    repo.add("leaf")
    with pytest.raises(MarkerError, match="tracked leaf"):
        capture_snapshot(repo.path / "leaf")
