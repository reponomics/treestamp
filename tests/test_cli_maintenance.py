"""Regression coverage for maintenance command behavior."""

import os
from dataclasses import replace
from itertools import product

import pytest

from tests.cli_fixtures import stamp
from tests.conftest import Repo, run_cli
from treestamp.document import load_document, parse_document, write_document


def test_check_update_idempotence_and_unbounded_additions(repo: Repo) -> None:
    path = stamp(repo)
    assert run_cli("check")[0] == 0
    for index in range(30):
        repo.write(f"src/new{index}.py")
    repo.add("src")
    before = path.read_bytes()
    code, out, err = run_cli("check")
    assert code == 1 and "new29.py" in out and not err
    assert path.read_bytes() == before
    assert run_cli("update")[0] == 0
    assert run_cli("check")[0] == 0
    updated = path.read_bytes()
    assert run_cli("update")[0] == 0 and path.read_bytes() == updated


@pytest.mark.parametrize("eol", [b"\n", b"\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize(
    "boundary",
    [b"<!-- treestamp:start -->\n\n", b"-->\n\n```sh", b"\n\n<!-- treestamp:end -->"],
)
def test_excess_blank_lines_still_participate_in_check(
    repo: Repo, eol: bytes, boundary: bytes
) -> None:
    path = stamp(repo, hidden=frozenset({"README.md"}))
    baseline = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", eol)
    path.write_bytes(baseline)
    assert run_cli("check")[0] == 0
    boundary = boundary.replace(b"\n", eol)
    original = baseline.replace(boundary, boundary.replace(eol * 2, eol * 3))
    assert original != baseline
    path.write_bytes(original)
    assert run_cli("check")[0] == 1
    assert path.read_bytes() == original
    assert run_cli("update")[0] == 0
    assert path.read_bytes() != original
    assert run_cli("check")[0] == 0


@pytest.mark.parametrize("gaps", list(product((False, True), repeat=3)))
@pytest.mark.parametrize("eol", [b"\n", b"\r\n"])
def test_check_accepts_optional_blank_lines_but_detects_stale_tree(
    repo: Repo,
    gaps: tuple[bool, bool, bool],
    eol: bytes,
) -> None:
    path = stamp(repo, hidden=frozenset({"README.md"}))
    original = path.read_bytes().replace(b"\r\n", b"\n")
    boundaries = [
        b"<!-- treestamp:start -->\n\n",
        b"-->\n\n```sh",
        b"\n\n<!-- treestamp:end -->",
    ]
    for boundary, keep in zip(boundaries, gaps, strict=True):
        if not keep:
            original = original.replace(boundary, boundary.replace(b"\n\n", b"\n"))
    original = original.replace(b"\n", eol)
    path.write_bytes(original)
    assert run_cli("check")[0] == 0
    assert run_cli("update")[0] == 0
    assert path.read_bytes() == original
    repo.write("new.py")
    repo.add("new.py")
    assert run_cli("check")[0] == 1
    assert path.read_bytes() == original
    assert run_cli("update")[0] == 0
    updated = path.read_bytes()
    for boundary, keep in zip(boundaries, gaps, strict=True):
        assert (boundary.replace(b"\n", eol) in updated) == keep
    assert run_cli("check")[0] == 0


def test_explicit_hidden_survives_maintenance(repo: Repo) -> None:
    path = stamp(repo, hidden=frozenset({"README.md"}))
    assert run_cli("check")[0] == 0
    document, _ = load_document(path)
    assert document is not None and "README.md" not in {
        n.path for n in document.tree.walk()
    }


@pytest.mark.parametrize("eol", [b"\n", b"\r\n"])
def test_check_accepts_authored_toml_without_hiding_tree_drift(
    repo: Repo, eol: bytes
) -> None:
    path = stamp(repo, hidden=frozenset({"README.md"}))
    payload = b"root = '.'\nhidden = [\n  'README.md', # intentionally hidden\n]\n"
    original = path.read_bytes().replace(b"\r\n", b"\n")
    original = original.replace(b'hidden = ["README.md"]\n', payload)
    original = original.replace(b"\n", eol)
    path.write_bytes(original)
    assert run_cli("check")[0] == 0
    assert run_cli("update")[0] == 0
    assert path.read_bytes() == original
    repo.write("new.py")
    repo.add("new.py")
    assert run_cli("check")[0] == 1
    assert path.read_bytes() == original
    assert run_cli("update")[0] == 0
    assert payload.replace(b"\n", eol) in path.read_bytes()
    assert run_cli("check")[0] == 0


def test_attribution_survives_check_update_and_print(repo: Repo) -> None:
    path = stamp(repo)
    document, _ = load_document(path)
    assert document is not None
    write_document(
        replace(document, settings=replace(document.settings, attribution=True)), path
    )
    assert run_cli("check")[0] == 0
    repo.write("src/new.py")
    repo.add("src/new.py")
    assert run_cli("check")[0] == 1
    assert run_cli("update")[0] == 0
    maintained, _ = load_document(path)
    assert maintained is not None and maintained.settings.attribution
    assert "src/new.py" in {node.path for node in maintained.tree.walk()}
    assert run_cli("check")[0] == 0
    code, output, error = run_cli("load", "README.md", "--print")
    assert code == 0 and not error
    assert parse_document(output.encode()).settings.attribution


@pytest.mark.parametrize("command", ["update", "check"])
@pytest.mark.parametrize("flag", ["--target", "--compare"])
def test_removed_snapshot_flags_never_write(
    repo: Repo, command: str, flag: str
) -> None:
    path = stamp(repo)
    before = path.read_bytes()
    with pytest.raises(SystemExit) as error:
        run_cli(command, flag, "HEAD")
    assert error.value.code == 2
    assert path.read_bytes() == before


def test_maintenance_uses_index_and_excludes_unstaged_additions(repo: Repo) -> None:
    path = stamp(repo)
    staged = "staged.txt"
    untracked = "untracked.txt"
    repo.write(staged)
    repo.write(untracked)
    repo.add(staged)
    assert run_cli("check")[0] == 1
    assert run_cli("update")[0] == 0
    document, _ = load_document(path)
    assert document is not None
    paths = {node.path for node in document.tree.walk()}
    assert staged in paths and untracked not in paths
    assert run_cli("check")[0] == 0


@pytest.mark.parametrize("absolute", [False, True])
def test_maintenance_uses_document_repository_index(
    repo: Repo,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
    absolute: bool,
) -> None:
    path = stamp(repo)
    repo.git("mv", "src/main.py", "src/renamed.py")
    other = Repo(tmp_path_factory.mktemp("unrelated"))
    other.git("init", "-q")
    monkeypatch.chdir(other.path)
    value = str(path) if absolute else os.path.relpath(path)
    assert run_cli("check", value)[0] == 1
    assert run_cli("update", value)[0] == 0
    document, _ = load_document(path)
    assert document is not None
    nodes = {node.path for node in document.tree.walk()}
    assert "src/renamed.py" in nodes and "src/main.py" not in nodes
    assert run_cli("check", value)[0] == 0
