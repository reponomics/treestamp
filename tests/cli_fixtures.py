"""Shared Git fixtures for command behavior tests."""

from dataclasses import replace
from pathlib import Path

from tests.conftest import Repo
from treestamp.document import Document, write_document
from treestamp.gitio import capture_snapshot


def stamp(repo: Repo, *, hidden: frozenset[str] = frozenset()) -> Path:
    path = repo.write("README.md", "<!-- treestamp:start -->\n<!-- treestamp:end -->\n")
    repo.write("src/main.py", "original content\n" * 20)
    repo.add(".")
    target = capture_snapshot(repo.path)
    tree = replace(
        target.tree,
        children=tuple(
            node for node in target.tree.children if node.path not in hidden
        ),
    )
    write_document(Document(tree, hidden=hidden), path)
    repo.add("README.md")
    repo.commit()
    return path
