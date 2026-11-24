"""Run the tests that correspond to changed files; the full suite when unsure.

Used by the pre-commit hooks. Source modules select their matching test file
and any suffixed test files. Core CLI and TUI modules select their whole test
family; a changed test file runs itself. Shared helpers, configuration, and
sources without matching tests select the project's full suite.

    python scripts/changed_tests.py {package|web} FILE...
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Modules whose behavior reaches every test; a change there runs everything.
SHARED = {"model", "errors", "session", "config", "conftest", "__init__"}
PROJECTS = {
    "package": (Path("src/treestamp"), Path("tests"), Path(".")),
    "web": (Path("web/src/treestamp_web"), Path("web/tests"), Path("web")),
}


def counterparts(project: str, module: str, tests: Path) -> set[Path]:
    """Include split suites, grouping the core CLI and TUI by interface."""
    family = module.split("_", 1)[0]
    if project != "package" or family not in {"cli", "tui"}:
        family = module
    matches = set(tests.glob(f"test_{family}_*.py"))
    names = [f"test_{family}.py"]
    if project == "package" and family == "cli":
        names.extend(("test_paths.py", "test_output_bytes.py"))
    matches.update(tests / name for name in names if (tests / name).is_file())
    return matches


def select(project: str, changed: list[str]) -> list[Path] | None:
    """Test files to run, or None for the full suite."""
    source, tests, _ = PROJECTS[project]
    selected: set[Path] = set()
    for name in changed:
        path = Path(name)
        if path.parent == tests and path.name.startswith("test_"):
            if path.exists():
                selected.add(path)
        elif path.is_relative_to(tests) and path.suffix == ".py":
            # conftest.py, __init__.py, helpers: shared by every test in the project.
            return None
        elif path.parent == source and path.suffix == ".py":
            if path.stem in SHARED:
                return None
            matches = counterparts(project, path.stem, tests)
            if not matches:
                return None
            selected.update(matches)
        elif path.is_relative_to(source) or path.is_relative_to(tests):
            continue  # static assets and non-Python files beneath the source tree
        else:
            return None
    return sorted(selected)


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in PROJECTS:
        print(__doc__, file=sys.stderr)
        return 2
    project, changed = argv[0], argv[1:]
    _, _, cwd = PROJECTS[project]
    chosen = select(project, changed)
    if chosen == []:
        print(f"{project}: no tests correspond to the changed files")
        return 0
    # sys.executable unresolved: resolving it would follow the venv's symlink out.
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:warnings"]
    if chosen is None:
        print(f"{project}: running the full suite", flush=True)
    else:
        rel = [
            str(p.relative_to(cwd)) if p.is_relative_to(cwd) else str(p) for p in chosen
        ]
        print(f"{project}: running {' '.join(rel)}", flush=True)
        command.extend(rel)
    return subprocess.call(command, cwd=cwd)  # noqa: S603


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
