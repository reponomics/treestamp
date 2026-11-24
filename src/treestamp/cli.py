"""Command verbs, safe terminal output, and lazy interactive dispatch."""

from __future__ import annotations

import argparse
import difflib
import sys
import unicodedata
from importlib.metadata import version
from typing import TYPE_CHECKING

from treestamp.cli_inputs import new_editor, read_source
from treestamp.cli_maintenance import prepare_maintenance
from treestamp.document import publish_write
from treestamp.errors import ExecutionError, MarkerError, TreestampError

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

COMMANDS = ("new", "load", "update", "check", "help")


def _print_argument(parser: argparse.ArgumentParser, *, child: bool = False) -> None:
    parser.add_argument(
        "--print",
        dest="print_output",
        action="store_true",
        default=argparse.SUPPRESS if child else False,
        help="print the selected treestamp and exit without opening the editor",
    )


def _editor_commands(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    for command in ("new", "load"):
        creating = command == "new"
        child = commands.add_parser(
            command,
            help="create a fresh treestamp"
            if creating
            else "load a treestamped document",
            description=(
                "Create a fresh treestamp from the staged Git index. "
                "Stage changes before opening the editor."
                if creating
                else "Load a document into an updated editor draft. With --print, "
                "extract the stored treestamp exactly, without updating it."
            ),
        )
        child.add_argument(
            "path",
            nargs="?",
            metavar="DIRECTORY" if creating else "DOCUMENT",
            help=(
                "existing directory to use as the tree root "
                "(default: current directory)"
                if creating
                else "document path (default: README.md in the current directory)"
            ),
        )
        _print_argument(child, child=True)


def _maintenance_commands(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    for command in ("check", "update"):
        checking = command == "check"
        child = commands.add_parser(
            command,
            help="report proposed changes"
            if checking
            else "update a treestamped document",
            description=(
                "Report the automatic update as a diff without writing. "
                "Exit 1 if a change is needed, or 0 if current."
                if checking
                else "Update a treestamped document. Unmatched notes prevent writing "
                "unless --skip-notes-transfer explicitly permits their omission."
            ),
        )
        child.add_argument(
            "document",
            nargs="?",
            help="document path (default: README.md in the current directory)",
        )
        if not checking:
            child.add_argument(
                "--skip-notes-transfer",
                action="store_true",
                help="allow unmatched notes to be omitted from the updated document",
            )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="treestamp",
        description=(
            "Curate Git directory trees. With no command, load the current directory's "
            "README.md if it contains a treestamp; otherwise create a fresh tree here. "
            "Use --print to extract the stored treestamp or print the new tree."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"treestamp {version('treestamp')}"
    )
    parser.set_defaults(path=None)
    _print_argument(parser)
    commands = parser.add_subparsers(dest="command")
    _editor_commands(commands)
    _maintenance_commands(commands)
    help_command = commands.add_parser("help", help="show general or command help")
    help_command.add_argument(
        "help_command", metavar="COMMAND", nargs="?", choices=COMMANDS
    )
    return parser


def _maintain(args: argparse.Namespace) -> int:
    source = read_source(args.document)
    result = prepare_maintenance(source)
    assert source.saved is not None
    if result.unmatched:
        if args.command == "update" and not args.skip_notes_transfer:
            raise MarkerError(result.transfer_notice(), location=str(source.path))
        _diagnostic(result.transfer_notice())
    prepared = result.prepared
    if prepared.content == source.saved.content:
        _emit(f"Current: {source.path}\n")
        return 0
    if args.command == "check":
        before = source.saved.content.decode("utf-8", "replace").splitlines(
            keepends=True
        )
        after = prepared.content.decode("utf-8", "replace").splitlines(keepends=True)
        _emit(
            "".join(
                difflib.unified_diff(
                    before, after, fromfile=str(source.path), tofile=str(source.path)
                )
            )
        )
        return 1
    publish_write(prepared)
    _emit(f"Updated: {source.path}\n")
    return 0


def _explore(args: argparse.Namespace) -> int:
    if args.command == "new":
        editor = new_editor(args.path)
    else:
        source = read_source(args.path, allow_absent=args.command is None)
        if source.document is not None and args.print_output:
            _emit(source.region_text())
            return 0
        editor = source.editor() if source.document is not None else new_editor(None)
    if args.print_output:
        _emit(editor.region_text())
        return 0
    from treestamp.tui import explore

    if explore(editor):
        _emit(editor.region_text())
    return 0


def _terminal_text(text: str, stream: TextIO) -> str:
    """Escape terminal controls, preserving layout and raw redirected output."""
    if not stream.isatty():
        return text
    # CRLF is a line ending; a bare CR could overwrite already displayed text.
    return "".join(
        ascii(char)[1:-1]
        if char not in "\n\t" and unicodedata.category(char) in {"Cc", "Cs"}
        else char
        for char in text.replace("\r\n", "\n")
    )


def _emit(text: str) -> None:
    """Display safely on a terminal; preserve Git bytes/newlines through pipes."""
    text = _terminal_text(text, sys.stdout)
    stream = getattr(sys.stdout, "buffer", None)
    if stream is None:
        sys.stdout.write(text)
        return
    sys.stdout.flush()
    stream.write(text.encode("utf-8", "surrogateescape"))
    stream.flush()


def _diagnostic(text: str) -> None:
    print(_terminal_text(f"treestamp: {text}", sys.stderr), file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        parser = _parser()
        args = parser.parse_args(argv)
        if args.command == "help":
            target = [args.help_command] if args.help_command else []
            parser.parse_args([*target, "--help"])
        if args.command in ("check", "update"):
            if args.print_output:
                parser.error(
                    "--print is only available for new, load, or automatic startup"
                )
            return _maintain(args)
        return _explore(args)
    except TreestampError as exc:
        _diagnostic(str(exc))
        return exc.exit_code
    except (OSError, UnicodeError) as exc:
        _diagnostic(str(exc))
        return ExecutionError.exit_code
    except KeyboardInterrupt:
        return 130
