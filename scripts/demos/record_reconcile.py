"""Record the real placement workflow and verify its saved document."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from treestamp.document import load_document, write_document
from treestamp.editor import EditorController
from treestamp.gitio import capture_snapshot
from treestamp.model import Settings

ROOT = Path(__file__).resolve().parents[2]
TAPE = Path(__file__).with_name("reconcile.tape")
PREFIX = "# Project layout\n\nThe surrounding Markdown stays intact.\n\n"
SUFFIX = "\nEnd of the project layout.\n"
NOTES = {
    "tools": "Reporting utilities",
    "tools/formats/csv.py": "Read CSV reports",
    "tools/report.py": "Build monthly summaries",
}


def git(repository: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgSign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(repository),
            *args,
        ],
        check=True,
        capture_output=True,
    )


def prepare(repository: Path, output: Path) -> None:
    git(repository, "init", "-q")
    for path in ("old-tools/formats/csv.py", "old-tools/report.py", "retired.py"):
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# Example {path}\n", encoding="utf-8")
    git(repository, "add", ".")
    editor = EditorController(capture_snapshot(repository), Settings())
    for path in ("old-tools", "old-tools/formats"):
        editor.state.session.expand(path)
    for path, note in NOTES.items():
        old = path.replace("tools", "old-tools", 1)
        editor.state.session.set_annotation(old, note)
    editor.state.session.set_annotation(
        "retired.py", "Retired helper; no longer needed"
    )
    write_document(editor.document(), repository / "tree.md", create=True)
    document = repository / "tree.md"
    document.write_text(PREFIX + document.read_text() + SUFFIX, encoding="utf-8")
    git(repository, "mv", "old-tools", "tools")
    git(repository, "rm", "-f", "retired.py")
    (output / "before.md").write_bytes(document.read_bytes())
    launcher = repository / "run-demo"
    launcher.write_text(
        "#!/bin/sh\n"
        f"{shlex.quote(sys.executable)} -m treestamp load tree.md\n"
        "capture_status=$?\n"
        "printf '%s\\n' \"$capture_status\" > "
        f"{shlex.quote(str(output / 'app-exit.txt'))}\n"
        "printf '\\nCAPTURE_FINISHED\\n'\n"
        'exit "$capture_status"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o700)


def record(argv: list[str], repository: Path, output: Path) -> None:
    with (output / "vhs.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            argv,
            cwd=repository,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            returncode = process.wait(timeout=240)
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
        if returncode:
            raise RuntimeError(f"VHS exited {returncode}; inspect {output / 'vhs.log'}")


def verify(repository: Path, output: Path) -> dict[str, object]:
    document, _ = load_document(repository / "tree.md")
    assert document is not None
    annotations = {
        node.path: node.annotation for node in document.tree.walk() if node.annotation
    }
    assert annotations == NOTES, annotations
    content = (repository / "tree.md").read_text(encoding="utf-8")
    assert content.startswith(PREFIX) and content.endswith(SUFFIX)
    assert "retired.py" not in content and "old-tools" not in content
    assert (output / "app-exit.txt").read_text().strip() == "0"
    checked = subprocess.run(
        [sys.executable, "-m", "treestamp", "check", "tree.md"],
        cwd=repository,
        capture_output=True,
        text=True,
        check=True,
    )
    (output / "after.md").write_text(content, encoding="utf-8")
    return {
        "application_exit": 0,
        "check_exit": checked.returncode,
        "check_output": checked.stdout.strip(),
        "annotations": annotations,
        "surrounding_markdown_preserved": True,
        "retired_annotation_omitted": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/reconcile-demo")
    parser.add_argument("--vhs", default="vhs")
    parser.add_argument("--frames", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # The fixture's Git context must not inherit a caller's repository/index.
    for name in tuple(os.environ):
        if name.startswith("GIT_"):
            os.environ.pop(name)
    os.environ["VHS_PUBLISH"] = "false"
    os.environ["PYTHONPATH"] = str(ROOT / "src")
    os.environ["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]
    )
    media = output / ("frames.png" if args.frames else "reconcile.mp4")
    if media.exists():
        parser.error("Media already exists; choose a fresh --output directory.")
    sources = {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (ROOT / "src/treestamp").glob("*.py")
    }
    tape_hash = hashlib.sha256(TAPE.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(
        prefix="ts-demo-",
        dir=Path("/tmp" if Path("/tmp").is_dir() else tempfile.gettempdir()).resolve(),
    ) as directory:
        repository = Path(directory).resolve()
        prepare(repository, output)
        record([args.vhs, str(TAPE), "--output", str(media)], repository, output)
        proof = verify(repository, output)
    proof["source_sha256"] = sources
    proof["tape_sha256"] = tape_hash
    proof["revision"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    proof["vhs_version"] = subprocess.check_output(
        [args.vhs, "--version"], text=True
    ).strip()
    (output / "proof.json").write_text(
        json.dumps(proof, indent=2) + "\n", encoding="utf-8"
    )
    if not media.exists():
        raise RuntimeError(
            "VHS completed without media; retry --frames in a fresh output directory"
        )
    print(f"Recorded and verified: {media}")


if __name__ == "__main__":
    main()
