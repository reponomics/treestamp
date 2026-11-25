"""Terminal output is safe to display; redirected output remains lossless."""

import io
import sys
import unicodedata

import pytest

from tests.conftest import Repo
from treestamp import cli
from treestamp.document import Document, write_document
from treestamp.errors import MarkerError
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings


@pytest.mark.parametrize("terminal", [False, True])
@pytest.mark.parametrize("binary", [False, True])
def test_output_controls_and_layout(
    monkeypatch: pytest.MonkeyPatch, terminal: bool, binary: bool
) -> None:
    controls = "".join(chr(code) for code in range(160) if code not in (9, 10, 13))
    text = f"└── café\tfile\r\n{controls}\rbyte\udcff\n"
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="utf-8") if binary else io.StringIO()
    monkeypatch.setattr(stream, "isatty", lambda: terminal)
    monkeypatch.setattr(sys, "stdout", stream)

    cli._emit(text)

    if binary:
        output = buffer.getvalue().decode("utf-8", "surrogateescape")
    else:
        assert isinstance(stream, io.StringIO)
        output = stream.getvalue()
    if terminal:
        assert output.startswith("└── café\tfile\n")
        assert output.endswith(r"\rbyte\udcff" + "\n")
        assert r"\x1b" in output
        assert all(
            char in "\n\t" or unicodedata.category(char) not in {"Cc", "Cs"}
            for char in output
        )
    else:
        assert output == text


@pytest.mark.parametrize("terminal", [False, True])
@pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])
def test_check_sanitizes_surrounding_document_context_only_for_terminal(
    repo: Repo, monkeypatch: pytest.MonkeyPatch, terminal: bool, eol: str
) -> None:
    path = repo.write("README.md", "<!-- treestamp:start -->\n<!-- treestamp:end -->\n")
    repo.add(".")
    write_document(
        Document(capture_snapshot(repo.path).tree, Settings(show_counts=False)), path
    )
    context = f"context: \x1b[31mred\x1b[0m{eol}"
    # A valid compact region keeps the outside text within unified diff context.
    compact = path.read_text(encoding="utf-8").replace(
        "\n\n<!-- treestamp:end -->", "\n<!-- treestamp:end -->"
    )
    path.write_bytes((compact.replace("\n", eol) + context).encode("utf-8"))
    repo.write("added.txt")
    repo.add(".")
    before = path.read_bytes()
    output = io.StringIO()
    monkeypatch.setattr(output, "isatty", lambda: terminal)
    monkeypatch.setattr(sys, "stdout", output)

    assert cli.main(["check"]) == 1

    diff = output.getvalue()
    assert "added.txt" in diff
    expected = r"context: \x1b[31mred\x1b[0m" + "\n" if terminal else context
    assert expected in diff
    assert ("\x1b" not in diff) == terminal
    assert path.read_bytes() == before


@pytest.mark.parametrize("terminal", [False, True])
@pytest.mark.parametrize("error_type", [MarkerError, OSError])
def test_error_output_observes_stderr_terminal_independently(
    monkeypatch: pytest.MonkeyPatch, terminal: bool, error_type: type[Exception]
) -> None:
    message = "untrusted \x1b[2J text"

    def fail(*args: object) -> None:
        raise error_type(message)

    output = io.StringIO()
    monkeypatch.setattr(output, "isatty", lambda: terminal)
    monkeypatch.setattr(sys, "stderr", output)
    monkeypatch.setattr(cli, "_maintain", fail)

    assert cli.main(["check"]) != 0

    expected = message.replace("\x1b", r"\x1b") if terminal else message
    assert output.getvalue() == f"treestamp: {expected}\n"
