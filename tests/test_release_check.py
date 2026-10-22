"""Publication checks reject private material and incomplete distributions."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_check.py"
spec = importlib.util.spec_from_file_location("release_check", SCRIPT)
assert spec is not None and spec.loader is not None
release_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_check)

WHEEL = Path("treestamp-0.1.0-py3-none-any.whl")
SDIST = Path("treestamp-0.1.0.tar.gz")


@pytest.mark.parametrize("artifact", [WHEEL, SDIST])
@pytest.mark.parametrize(
    "extra",
    [
        "docs/planning/initial-release-plan.md",
        "web/src/treestamp_web/app.py",
        "palette.css",
        ".env",
        "venv/bin/python",
        "scripts/private_notes.md",
        "src/treestamp/__pycache__/cli.pyc",
    ],
)
def test_unapproved_files_rejected(artifact: Path, extra: str) -> None:
    names = release_check.expected_contents(artifact)
    prefix = "treestamp-0.1.0/" if artifact == SDIST else ""
    names.add(prefix + extra)
    with pytest.raises(ValueError, match="unexpected packaged files"):
        release_check.verify_contents(names, artifact)


@pytest.mark.parametrize(
    ("artifact", "missing"),
    [
        (WHEEL, "treestamp/editor.py"),
        (WHEEL, "treestamp/py.typed"),
        (WHEEL, "treestamp-0.1.0.dist-info/licenses/LICENSE"),
        (SDIST, "treestamp-0.1.0/pyproject.toml"),
        (SDIST, "treestamp-0.1.0/PRIVACY.md"),
        (SDIST, "treestamp-0.1.0/tests/test_cli.py"),
        (SDIST, "treestamp-0.1.0/scripts/installed_editor_check.py"),
    ],
)
def test_required_files_missing(artifact: Path, missing: str) -> None:
    names = release_check.expected_contents(artifact)
    names.remove(missing)
    with pytest.raises(ValueError, match="missing packaged files"):
        release_check.verify_contents(names, artifact)


def test_source_archive_has_one_matching_root() -> None:
    names = release_check.expected_contents(SDIST)
    names.remove("treestamp-0.1.0/README.md")
    names.add("other-project-0.1.0/README.md")
    with pytest.raises(ValueError, match="unexpected packaged files"):
        release_check.verify_contents(names, SDIST)
