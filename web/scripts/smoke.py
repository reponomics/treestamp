"""Post-deploy check: the hosted region must equal a local render byte for byte.

    python web/scripts/smoke.py https://host [--repo owner/name]
        [--checkout PATH]

Previews the repository's default branch, then renders the same commit from
the checkout, which must contain it. Exit 0 only on byte identity.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from treestamp.document import Document, render_region  # noqa: E402
from treestamp.gitio import capture_snapshot  # noqa: E402
from treestamp.model import Settings, repo_path  # noqa: E402
from treestamp.session import TreeSession  # noqa: E402


def fetch(url: str) -> tuple[int, dict[str, object]]:
    request = Request(url, headers={"User-Agent": "treestamp-smoke"})
    try:
        with urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except Exception as exc:  # noqa: BLE001
        status = getattr(exc, "code", 0)
        body = getattr(exc, "read", lambda: b"{}")()
        try:
            return status, json.loads(body)
        except ValueError:
            return status, {"error": str(exc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", help="base URL of the deployed service")
    parser.add_argument("--repo", default="reponomics/treestamp", metavar="OWNER/NAME")
    parser.add_argument("--checkout", default=".")
    args = parser.parse_args(argv)
    base = args.base.rstrip("/")
    checkout = Path(args.checkout).resolve()
    local_head = subprocess.run(  # noqa: S603
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    status, health = fetch(f"{base}/healthz")
    print(f"healthz: {status} {json.dumps(health)}")
    if status != 200:
        return 1
    budget = health.get("budget") if isinstance(health.get("budget"), dict) else {}
    if not health.get("token_configured") or budget.get("limit") not in (None, 5000):
        print("warning: token not configured or budget limit is not 5000")

    owner, name = args.repo.split("/", 1)
    settings = Settings()
    query = urlencode(
        {
            "owner": owner,
            "repo": name,
            "ref": "HEAD",
            "document": "",
        }
    )
    status, preview = fetch(f"{base}/api/preview?{query}")
    if status != 200:
        print(f"preview failed: {status} {json.dumps(preview)}")
        return 1
    region = preview.get("region")
    if not isinstance(region, str):
        print(f"preview has no region: warnings={preview.get('warnings')}")
        return 1
    ref = preview.get("ref")
    commit = str(ref.get("commit")) if isinstance(ref, dict) else ""
    if commit != local_head:
        print(f"warning: service saw {commit[:12]}, checkout is at {local_head[:12]}")

    root = str(preview.get("root") or ".")
    try:
        snapshot = capture_snapshot(
            checkout if root == "." else checkout / root, commit
        )
    except Exception as exc:  # noqa: BLE001
        print(f"cannot render {commit[:12]} from the checkout: {exc}")
        print("fetch the commit or check out the deployed revision, then retry")
        return 1
    session = TreeSession(snapshot.tree, settings)
    document = Document(
        session.printed_tree(),
        settings,
        frozenset(repo_path(path, root) for path in session.saved_hidden()),
    )
    local = render_region(document, ".")
    if region.encode("utf-8") == local.encode("utf-8", "surrogateescape"):
        print(f"byte identity confirmed for {args.repo}@{commit[:12]}")
        return 0
    print("mismatch between hosted region and local render")
    for index, (a, b) in enumerate(
        zip(region.splitlines(), local.splitlines(), strict=False)
    ):
        if a != b:
            print(f"first difference at line {index + 1}:")
            print(f"  hosted: {a!r}\n  local:  {b!r}")
            break
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
