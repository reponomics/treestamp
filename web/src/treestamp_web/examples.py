"""Shipped offline fixtures, never authorization to fetch historical objects."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from treestamp.sources import TreeRecord
from treestamp_web.github import Resolved
from treestamp_web.links import Repository


@cache
def _trees() -> dict[Repository, tuple[Resolved, list[TreeRecord]]]:
    data = json.loads(
        (Path(__file__).parent / "data" / "examples.json").read_text(encoding="utf-8")
    )
    return {
        Repository("reponomics", name, tree["commit"]): (
            Resolved(tree["commit"], tree["tree"]),
            [
                TreeRecord(row["path"], row["mode"], row["type"], row["sha"])
                for row in tree["entries"]
            ],
        )
        for name, tree in data.items()
    }


def bundled_tree(repo: Repository) -> tuple[Resolved, list[TreeRecord]] | None:
    return _trees().get(repo)


@cache
def _branches() -> dict[Repository, str]:
    data = json.loads(
        (Path(__file__).parent / "data" / "examples.json").read_text(encoding="utf-8")
    )
    return {
        Repository("reponomics", name, tree["commit"]): tree["default_branch"]
        for name, tree in data.items()
        if isinstance(tree.get("default_branch"), str)
    }


def bundled_default_branch(repo: Repository) -> str | None:
    return _branches().get(repo)
