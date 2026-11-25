"""The pre-commit test selector picks the right tests for changed files."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "changed_tests.py"
spec = importlib.util.spec_from_file_location("changed_tests", SCRIPT)
assert spec is not None and spec.loader is not None
changed_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(changed_tests)


@pytest.mark.parametrize(
    ("project", "changed", "expected"),
    [
        ("package", ["src/treestamp/codec.py"], [Path("tests/test_codec.py")]),
        (
            "package",
            ["tests/test_cli.py", "src/treestamp/codec.py"],
            [Path("tests/test_cli.py"), Path("tests/test_codec.py")],
        ),
        ("package", ["src/treestamp/model.py"], None),
        ("package", ["tests/conftest.py"], None),
        ("package", ["tests/__init__.py"], None),
        ("package", ["pyproject.toml"], None),
        ("web", ["web/tests/conftest.py"], None),
        ("web", ["web/tests/browser/conftest.py"], None),
        ("web", ["web/src/treestamp_web/links.py"], [Path("web/tests/test_links.py")]),
        ("web", ["web/src/treestamp_web/static/app.js"], []),
        ("web", ["web/tests/js/logic.test.mjs"], []),
    ],
)
def test_selection(
    project: str, changed: list[str], expected: list[Path] | None
) -> None:
    assert changed_tests.select(project, changed) == expected


@pytest.mark.parametrize(
    "module",
    [
        "cli",
        "cli_inputs",
        "cli_maintenance",
        "tui",
        "tui_dialogs",
        "tui_reconcile",
        "tui_rows",
    ],
)
def test_interface_modules_select_all_split_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: str
) -> None:
    monkeypatch.chdir(tmp_path)
    tests = Path("tests")
    tests.mkdir()
    family = module.split("_", 1)[0]
    expected = [
        tests / f"test_{family}{suffix}.py" for suffix in ("", "_startup", "_output")
    ]
    if family == "cli":
        expected.extend((tests / "test_paths.py", tests / "test_output_bytes.py"))
    for path in [
        *expected,
        tests / f"test_{family}unrelated.py",
        tests / "test_other.py",
    ]:
        path.touch()
    assert changed_tests.select(
        "package", [f"src/treestamp/{module}.py", str(expected[0])]
    ) == sorted(expected)


@pytest.mark.parametrize("project", ["package", "web"])
def test_split_suite_without_original_file_is_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project: str
) -> None:
    monkeypatch.chdir(tmp_path)
    source, tests, _ = changed_tests.PROJECTS[project]
    tests.mkdir(parents=True)
    expected = [tests / "test_document_parsing.py", tests / "test_document_writes.py"]
    for path in expected:
        path.touch()
    assert changed_tests.select(project, [str(source / "document.py")]) == expected
    assert changed_tests.select(project, [str(source / "unknown.py")]) is None


@pytest.mark.parametrize("child", [False, True])
@pytest.mark.parametrize("explicit", [False, True])
def test_hook_enforces_encoding_in_tests_and_subprocesses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
    child: bool,
    explicit: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    # A caller's permissive filter must not disable this check.
    monkeypatch.setenv("PYTHONWARNINGS", "ignore::EncodingWarning")
    monkeypatch.setenv("PYTHONWARNDEFAULTENCODING", "0")
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)
    tests = tmp_path / "tests"
    tests.mkdir()
    probe = tests / "test_encoding.py"
    read = "Path('payload').read_text(" + ('encoding="utf-8"' if explicit else "") + ")"
    code = "from pathlib import Path; " + read
    body = (
        f"subprocess.run([sys.executable, '-c', {code!r}], check=True)"
        if child
        else read
    )
    probe.write_text(
        "import subprocess, sys\nfrom pathlib import Path\n"
        f"def test_read():\n    {body}\n",
        encoding="utf-8",
    )
    (tmp_path / "payload").write_text("tree", encoding="utf-8")

    result = changed_tests.main(["package", "tests/test_encoding.py"])

    assert result == (0 if explicit else 1)
    output = capfd.readouterr()
    if not explicit:
        assert "EncodingWarning" in output.out + output.err
