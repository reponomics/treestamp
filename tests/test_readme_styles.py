"""Keep README previews in sync without changing the managed document or prose."""

import importlib.util
from pathlib import Path

import pytest

from treestamp.document import parse_document

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "readme_styles.py"
spec = importlib.util.spec_from_file_location("readme_styles", SCRIPT)
assert spec and spec.loader
styles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(styles)

SOURCE = """Introduction.
<!-- treestamp:start -->
<!-- treestamp:config
hidden = ["secret"]
-->
```sh
./
├── src/ (2 files)  # Application
└── README.md  # Start here
```

Maintained with [treestamp](https://github.com/reponomics/treestamp)
<!-- treestamp:end -->

Other prose.
<!-- readme-styles:start -->
stale previews
<!-- readme-styles:end -->
Conclusion.
"""


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_refresh_preserves_document_and_surroundings(eol: str) -> None:
    original = SOURCE.replace("\n", eol).encode()
    updated = styles.refreshed_content(original)
    assert parse_document(updated) == parse_document(original)
    assert (
        updated.split(b"<!-- readme-styles:start -->")[0]
        == original.split(b"<!-- readme-styles:start -->")[0]
    )
    assert (
        updated.split(b"<!-- readme-styles:end -->")[1]
        == original.split(b"<!-- readme-styles:end -->")[1]
    )
    assert b"|-- src/ (2 files)  # Application" in updated
    assert b"- src/ (2 files)  # Application" in updated
    assert updated.count(b"Start here") == 3
    assert updated.count(b"Maintained with") == 3
    assert updated.count(b"<!-- treestamp:start -->") == 1
    assert updated.count(b"secret") == 1  # Metadata is not displayed in previews.
    if eol == "\r\n":
        assert b"\n" not in updated.replace(b"\r\n", b"")
    assert styles.refreshed_content(updated) == updated


def test_footer_setting_is_shared() -> None:
    source = SOURCE.replace(
        "Maintained with [treestamp](https://github.com/reponomics/treestamp)\n", ""
    )
    assert b"Maintained with" not in styles.refreshed_content(source.encode())


def test_check_reports_drift_without_writing_and_write_repairs(tmp_path: Path) -> None:
    path = tmp_path / "README.md"
    path.write_bytes(SOURCE.encode())
    assert styles.main([str(path)]) == 1
    assert path.read_bytes() == SOURCE.encode()
    assert styles.main(["--write", str(path)]) == 0
    assert styles.main([str(path)]) == 0
    changed = path.read_bytes().replace(b"Application", b"New annotation", 1)
    path.write_bytes(changed)
    assert styles.main([str(path)]) == 1
    assert path.read_bytes() == changed
    assert styles.main(["--write", str(path)]) == 0
    assert path.read_bytes().count(b"New annotation") == 3


@pytest.mark.parametrize(
    "source",
    [
        SOURCE.replace("<!-- readme-styles:start -->", ""),
        SOURCE + "<!-- readme-styles:start -->\n",
        SOURCE.replace("<!-- readme-styles:start -->", "<!-- readme-styles:end -->"),
        SOURCE.replace("<!-- treestamp:start -->", ""),
    ],
)
def test_invalid_input_is_not_overwritten(tmp_path: Path, source: str) -> None:
    path = tmp_path / "README.md"
    path.write_bytes(source.encode())
    assert styles.main(["--write", str(path)]) == 2
    assert path.read_bytes() == source.encode()
