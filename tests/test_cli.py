"""Regression coverage for cli command behavior."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import Repo, run_cli
from treestamp.cli import main


@pytest.mark.parametrize("command", [None, "new", "update", "check"])
@pytest.mark.parametrize(
    "flag",
    [
        "--show-counts",
        "--no-show-counts",
        "--count-mode",
        "--depth",
        "--max-children",
        "--style",
        "--hide-root-files",
        "--no-hide-root-files",
        "--exclude",
        "--hide",
        "--root",
        "--tree-only",
        "--strict",
        "--additions",
        "--moves",
        "--document",
    ],
)
def test_removed_flags_rejected(command: str | None, flag: str) -> None:
    with pytest.raises(SystemExit) as error:
        run_cli(*((command, flag) if command else (flag,)))
    assert error.value.code == 2


@pytest.mark.parametrize("prefix", [(), ("new",), ("load",), ("check",), ("update",)])
@pytest.mark.parametrize("flag", ["--target", "--compare"])
def test_snapshot_flags_are_rejected(prefix: tuple[str, ...], flag: str) -> None:
    with pytest.raises(SystemExit) as error:
        run_cli(*prefix, flag, "HEAD")
    assert error.value.code == 2


@pytest.mark.parametrize("name", [".", "render", "fix"])
def test_positional_repository_locations_are_rejected(repo: Repo, name: str) -> None:
    repo.write(f"{name}/file")
    repo.add(".")
    with pytest.raises(SystemExit) as error:
        run_cli(name, "--print")
    assert error.value.code == 2


@pytest.mark.parametrize("arguments", [["--help"], ["help"], ["help", "new"]])
def test_module_entrypoint_uses_cli_arguments(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
) -> None:
    import runpy

    monkeypatch.setattr(sys, "argv", ["treestamp", *arguments])
    with pytest.raises(SystemExit) as result:
        runpy.run_module("treestamp", run_name="__main__")
    assert result.value.code == 0
    captured = capsys.readouterr()
    assert "usage: treestamp" in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("command", [None, "new", "check", "update", "help"])
def test_help_alias_matches_flag_outside_repository(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str | None,
) -> None:
    monkeypatch.chdir(tmp_path)
    target = [command] if command else []
    with pytest.raises(SystemExit) as flag_exit:
        main([*target, "--help"])
    expected = capsys.readouterr()
    with pytest.raises(SystemExit) as alias_exit:
        main(["help", *target])
    actual = capsys.readouterr()
    assert flag_exit.value.code == alias_exit.value.code == 0
    assert actual.out == expected.out
    assert actual.out.startswith("usage: treestamp")
    assert actual.err == expected.err == ""
    if command is None:
        assert "help" in actual.out


@pytest.mark.parametrize(
    "arguments, diagnostic",
    [
        (["help", "unknown"], "invalid choice"),
        (["help", "new", "extra"], "unrecognized arguments"),
        (["help", "check", "README.md"], "unrecognized arguments"),
        (["help", "--print"], "unrecognized arguments"),
    ],
)
def test_help_rejects_invalid_arguments(
    arguments: list[str], diagnostic: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as result:
        main(arguments)
    captured = capsys.readouterr()
    assert result.value.code == 2
    assert not captured.out
    assert diagnostic in captured.err


@pytest.mark.parametrize("command", [None, "new", "check", "update", "help"])
def test_help_does_not_import_textual(tmp_path: Path, command: str | None) -> None:
    arguments = ["help", command] if command else ["help"]
    source = str(Path(__file__).resolve().parents[1] / "src")
    script = f"""
import sys
from treestamp.cli import main
try:
    main({arguments!r})
except SystemExit as exc:
    assert exc.code == 0
else:
    raise AssertionError("help must exit successfully")
assert not any(k == 'textual' or k.startswith('textual.') for k in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": source},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage: treestamp")
    assert not result.stderr


@pytest.mark.parametrize(
    "arguments", [("tui",), ("--load", "README.md"), ("load", "--load", "README.md")]
)
def test_superseded_editor_syntax_is_rejected(arguments: tuple[str, ...]) -> None:
    with pytest.raises(SystemExit) as error:
        run_cli(*arguments)
    assert error.value.code == 2


@pytest.mark.parametrize("command", ["check", "update"])
def test_print_cannot_silently_change_maintenance_semantics(command: str) -> None:
    with pytest.raises(SystemExit) as error:
        run_cli("--print", command)
    assert error.value.code == 2


@pytest.mark.parametrize("command", ["new", "load", "check"])
def test_skip_notes_transfer_only_applies_to_update(command: str) -> None:
    with pytest.raises(SystemExit) as error:
        run_cli(command, "--skip-notes-transfer")
    assert error.value.code == 2
