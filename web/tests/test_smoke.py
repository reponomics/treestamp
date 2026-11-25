"""Hosted parity checks require matching index facts and never rewrite the index."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

from .conftest import Repo

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke.py"
spec = importlib.util.spec_from_file_location("smoke", SCRIPT)
assert spec is not None and spec.loader is not None
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


def test_matching_index_accepts_unstaged_changes(repo: Repo) -> None:
    repo.write("tracked", "committed")
    commit = repo.commit()
    repo.write("tracked", "unstaged")
    repo.write("untracked")
    index = repo.path / ".git" / "index"
    before = index.read_bytes()
    smoke.verify_index(repo.path, commit)
    assert index.read_bytes() == before


def test_mismatching_index_is_rejected_without_modification(repo: Repo) -> None:
    repo.write("tracked", "committed")
    commit = repo.commit()
    repo.write("staged")
    repo.git("add", "staged")
    index = repo.path / ".git" / "index"
    before = index.read_bytes()
    with pytest.raises(subprocess.CalledProcessError):
        smoke.verify_index(repo.path, commit)
    assert index.read_bytes() == before


@pytest.mark.parametrize("ref", ["missing-ref", "--help"])
def test_unresolvable_hosted_commit_is_rejected(repo: Repo, ref: str) -> None:
    repo.commit()
    with pytest.raises(subprocess.CalledProcessError):
        smoke.verify_index(repo.path, ref)
