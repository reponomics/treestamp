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
        (
            "package",
            ["src/treestamp/tui_dialogs.py"],
            [Path("tests/test_tui_dialogs.py")],
        ),
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
