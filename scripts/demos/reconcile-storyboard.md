# Placing notes after a directory move

Viewer question: “Can I keep the notes in my project tree when a folder moves?”

The clip opens on the real terminal editor's load prompt. A disposable Git repository has a saved tree with four annotations: a reporting directory, two files beneath it (including a nested CSV reader), and a retired file. The directory has been renamed from `old-tools/` to `tools/`; `retired.py` was intentionally deleted. Fixture setup stays outside the recording.

| Beat | Visible action | Evidence |
| --- | --- | --- |
| Orient | Read the prompt reporting four displaced annotations | The application offers placement before editing |
| Place | Enter; select `tools/`; Enter | One directory decision carries its own note and both nested notes |
| Skip | Read the remaining `retired.py` item; press `s` | The intentionally deleted note is left out, and ordinary editing begins |
| Save | Press `w` to update the loaded `tree.md` | The populated tree and the application's write confirmation remain visible |

The tape uses 180 ms typing, deliberate key pauses, and a five-second final hold. The normal application UI is unchanged. There is no narration, mock service, network dependency, or production write.

The recorder independently parses the written document, checks all three relocated annotations and the absent retired annotation, checks unchanged surrounding Markdown, and verifies both the application and `treestamp check` exit successfully. This is separate from media validation.

From the repository root, reproduce with `PYTHONPATH=src venv/bin/python scripts/demos/record_reconcile.py`. Recordings and evidence go to ignored `output/reconcile-demo/`. `--vhs` selects the installed VHS executable; `--frames` selects native paired PNG output when the installed VHS encoder does not create its requested MP4. In that case compose the paired frames at the tape's original 15 fps using the demo-video-production skill's `media.py frames` command, preserving 1120×800 dimensions and padding 18.
