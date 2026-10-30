"""Headless maintenance and lazy dispatch to the interactive editor."""

from __future__ import annotations

import argparse
import difflib
import sys
from importlib.metadata import version
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

from treestamp.document import (
    DEFAULT_DOCUMENT_FILE,
    Document,
    load_document,
    prepare_write,
    publish_write,
    validate_source_tree,
)
from treestamp.errors import ExecutionError, MarkerError, TreestampError
from treestamp.gitio import (
    Snapshot,
    capture_snapshot,
    changes,
    checked_path,
    document_path,
    repo_root,
)
from treestamp.maintenance import update
from treestamp.model import Settings, build_tree, tree_path

if TYPE_CHECKING:
    from collections.abc import Sequence

    from treestamp.editor import EditorController

COMMANDS = ("tui", "update", "check")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="treestamp",
        description=(
            "Curate Git directory trees. With no command, open the editor. "
            "Use --load DOCUMENT to open an existing treestamp directly, or --print "
            "to print the complete treestamp without opening the editor."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"treestamp {version('treestamp')}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    editor = commands.add_parser(
        "tui",
        help="open the editor or print a treestamp",
        epilog=(
            "--load replaces --document. Positional repository paths are no longer "
            "accepted; use --load DOCUMENT to select a document's repository, "
            "or change directory before starting the editor."
        ),
    )
    editor.add_argument(
        "--load",
        metavar="DOCUMENT",
        help=(
            "open an existing treestamp directly; path is relative to cwd or absolute "
            "and selects its containing repository"
        ),
    )
    editor.add_argument(
        "--print",
        dest="print_output",
        action="store_true",
        help="print the complete treestamp and exit without writing a document",
    )
    for command in ("check", "update"):
        child = commands.add_parser(
            command,
            help=(
                "report whether Update would change a document"
                if command == "check"
                else "update a treestamped document"
            ),
        )
        child.add_argument(
            "document",
            nargs="?",
            help=(
                "document path relative to cwd or absolute; selects its repository "
                "(default: README.md at the root of cwd's repository)"
            ),
        )
        child.add_argument(
            "--target", metavar="REF", help="target Git ref (default: captured index)"
        )
        child.add_argument(
            "--compare", metavar="REF", help="reference for detected moves"
        )
    return parser


def _cli_document(value: str | None) -> tuple[Path, Path]:
    """Resolve shell paths once, then retain the editor's repository boundaries."""
    if value is None:
        repository = repo_root(Path.cwd())
        return repository, document_path(repository, DEFAULT_DOCUMENT_FILE)
    path = Path(value)
    windows = PureWindowsPath(value)
    if (
        not value
        or "\x00" in value
        or ((windows.drive or windows.root) and not path.is_absolute())
    ):
        raise MarkerError("document path must be a nonempty native filesystem path")
    # Inspect the original spelling before normalization can erase link/.. pairs.
    absolute = path.absolute()
    for parent in reversed(absolute.parents):
        checked_path(parent)
    destination = checked_path(absolute)
    if destination.is_dir():
        raise MarkerError("document path must name a file")
    repository = repo_root(destination)
    return repository, document_path(repository, destination.relative_to(repository))


def _maintain(args: argparse.Namespace) -> int:
    repository, path = _cli_document(args.document)
    document, previous = load_document(path)
    assert document is not None and previous is not None
    root = repository / document.settings.root
    target = capture_snapshot(root, args.target, repository=repository)
    validate_source_tree(target.tree, document.settings)
    if args.compare == "":
        raise MarkerError("--compare requires a nonempty ref")
    moves = changes(target, args.compare).moves if args.compare is not None else None
    hidden = frozenset(
        tree_path(path, document.settings.root) for path in document.hidden
    )
    tree = update(
        document.tree, target.tree, document.settings, hidden=hidden, moves=moves
    )
    maintained = Document(tree, document.settings, document.hidden)
    prepared = prepare_write(
        maintained, previous.path, expected=previous, repository=repository
    )
    if prepared.content == previous.content:
        _emit(f"Current: {previous.path}\n")
        return 0
    if args.command == "check":
        before = previous.content.decode("utf-8", "replace").splitlines(keepends=True)
        after = prepared.content.decode("utf-8", "replace").splitlines(keepends=True)
        _emit(
            "".join(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile=str(previous.path),
                    tofile=str(previous.path),
                )
            )
        )
        return 1
    publish_write(prepared)
    _emit(f"Updated: {previous.path}\n")
    return 0


def _editor_inputs(args: argparse.Namespace) -> EditorController:
    from treestamp.editor import EditorController

    repository, path = _cli_document(args.load)
    document, previous = load_document(path, allow_absent=args.load is None)
    settings = document.settings if document else Settings()
    target = capture_snapshot(repository / settings.root, repository=repository)
    return EditorController(
        target,
        settings,
        tree=document.tree if document else None,
        hidden=document.hidden if document else frozenset(),
        document_path=path,
        document_snapshot=previous,
        loaded_document=document,
    )


def _explore(args: argparse.Namespace) -> int:
    if args.print_output:
        _emit(_editor_inputs(args).region_text())
        return 0
    from treestamp.editor import EditorController
    from treestamp.tui import explore

    if args.load is not None:
        editor = _editor_inputs(args)
        startup_document = None
    else:
        repository = repo_root(Path.cwd())
        # New/Load captures its selected subtree only after the opening choice.
        editor = EditorController(
            Snapshot(repository, repository, build_tree([]), ""), Settings()
        )
        startup_document = Path(DEFAULT_DOCUMENT_FILE)
    if explore(editor, startup_document=startup_document):
        _emit(editor.region_text())
    return 0


def _emit(text: str) -> None:
    """Preserve Git bytes and newlines even through a Windows output pipe."""
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        sys.stdout.write(text)
        return
    sys.stdout.flush()
    stream.write(text.encode("utf-8", "surrogateescape"))
    stream.flush()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in (*COMMANDS, "--help", "-h", "--version"):
        arguments.insert(0, "tui")
    try:
        args = _parser().parse_args(arguments)
        if args.command == "tui":
            return _explore(args)
        return _maintain(args)
    except TreestampError as exc:
        print(f"treestamp: {exc}", file=sys.stderr)
        return exc.exit_code
    except (OSError, UnicodeError) as exc:
        print(f"treestamp: {exc}", file=sys.stderr)
        return ExecutionError.exit_code
    except KeyboardInterrupt:
        return 130
