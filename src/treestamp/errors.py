"""Failures shared by headless maintenance and the interactive editor.

Exit codes: 0 success, 1 check drift, 2 invalid input or curation constraint,
3 unavailable Git/filesystem facts, 130 interruption.
"""

from __future__ import annotations

EXIT_CLEAN = 0
EXIT_DRIFT = 1
EXIT_USAGE = 2
EXIT_ENVIRONMENT = 3
EXIT_INTERRUPT = 130


class TreestampError(Exception):
    """Base for all treestamp failures that carry an exit code."""

    exit_code = EXIT_USAGE

    def __init__(self, message: str, *, location: str | None = None) -> None:
        self.location = location
        super().__init__(f"{location}: {message}" if location else message)


class MarkerError(TreestampError):
    """Invalid document, settings, paths, or curation constraints. Exit 2."""

    exit_code = EXIT_USAGE


class ExecutionError(TreestampError):
    """An environment or filesystem operation could not complete. Exit 3."""

    exit_code = EXIT_ENVIRONMENT


class GitEnvironmentError(ExecutionError):
    """Not a git repository, or git not on PATH. Exit 3."""

    exit_code = EXIT_ENVIRONMENT
