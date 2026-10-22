"""Serve a local Git checkout through the GitHub API endpoints the client uses.

Run the service with GITHUB_API_URL pointed here to evaluate the page with no
network and no token. Flags synthesize failure modes.

    python web/scripts/fake_github.py --repo . --port 8100 [--truncated]
        [--rate-limit-after N] [--delay SECONDS] [--empty] [--only owner/repo]
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from treestamp_web.localgit import (  # noqa: E402
    FakeGitHub,
    FakeOptions,
    LocalRepository,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="Git checkout to serve")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--truncated", action="store_true")
    parser.add_argument("--rate-limit-after", type=int, default=None, metavar="N")
    parser.add_argument("--delay", type=float, default=0.0, metavar="SECONDS")
    parser.add_argument("--empty", action="store_true")
    parser.add_argument("--only", default=None, metavar="OWNER/REPO")
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args(argv)

    repository = LocalRepository(Path(args.repo).resolve())
    if repository.resolve("HEAD") is None:
        print(f"{args.repo} is not a Git checkout with a commit", file=sys.stderr)
        return 2
    fake = FakeGitHub(
        repository,
        FakeOptions(
            truncated=args.truncated,
            rate_limit_after=args.rate_limit_after,
            empty=args.empty,
            only=args.only,
            limit=args.limit,
        ),
    )
    delay = args.delay

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._serve("GET")

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            self._serve("POST")

        def _serve(self, method: str) -> None:
            parts = urlsplit(self.path)
            query = dict(parse_qsl(parts.query))
            accept = self.headers.get("Accept", "")
            if delay:
                time.sleep(delay)
            status, headers, body = fake.respond(
                parts.path,
                query,
                accept,
                method=method,
                authorization=self.headers.get("Authorization", ""),
            )
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            sys.stderr.write(f"fake-github {format % args}\n")

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(
        f"fake GitHub serving {repository.path} on http://127.0.0.1:{args.port} "
        f"(limit {args.limit}; every owner/repo maps to this checkout"
        f"{' except ' + args.only + ' only' if args.only else ''})"
    )
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
