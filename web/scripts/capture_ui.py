"""Capture a small UI gallery for visual review, not a visual pass/fail test.

Use an existing local preview; every viewport gets an isolated browser context.
Repository/document states use the configured fixture, while the editor uses the
bundled example. Missing states remain explicit gaps in manifest.json and HTML.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from playwright.sync_api import Browser, Page, sync_playwright

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).resolve().parents[2]
PROFILES = [
    ("phone", 320, 568, "dark"),
    ("tablet", 768, 1024, "light"),
    ("desktop", 1280, 900, "dark"),
    ("wide", 1680, 1050, "light"),
]


@dataclass
class Capture:
    profile: str
    state: str
    status: str = "not reached"
    image: str = ""
    detail: str = ""


class Gallery:
    def __init__(self, page: Page, profile: str, output: Path, deadline: float) -> None:
        self.page = page
        self.profile = profile
        self.output = output
        self.deadline = deadline
        self.captures: list[Capture] = []

    def take(self, state: str, action: Callable[[], None]) -> None:
        capture = Capture(self.profile, state)
        self.captures.append(capture)
        image_path = self.output / f"{self.profile}-{state}.png"
        image_path.unlink(missing_ok=True)
        if time.monotonic() >= self.deadline:
            capture.detail = "Capture time budget exhausted."
            return
        try:
            action()
            loaded = self.page.evaluate(
                "() => Promise.race([document.fonts.ready.then(() => true), "
                "new Promise(resolve => setTimeout(() => resolve(false), 1200))])"
            )
            if not loaded:
                raise RuntimeError("Fonts did not finish loading within 1.2 seconds.")
            capture.image = f"{self.profile}-{state}.png"
            self.page.screenshot(
                path=self.output / capture.image, animations="disabled", timeout=2000
            )
            capture.status = "captured"
        except Exception as exc:
            # A failed capture must not leave an old or partially written image.
            image_path.unlink(missing_ok=True)
            # Keep later states and the missing-state report useful.
            capture.status = "not reached"
            capture.detail = str(exc).split("Call log:", 1)[0].strip()[:600]
            capture.image = ""


def visible(page: Page, selector: str) -> None:
    page.locator(selector).first.wait_for(state="visible")


def show_welcome(page: Page, url: str) -> None:
    page.goto(url, wait_until="domcontentloaded")
    visible(page, "#entry-welcome")


def open_example(page: Page) -> None:
    page.locator("#explore-example").click()
    visible(page, "#rows .row")


def open_note(page: Page) -> None:
    # Exercise a real long filename without replacing app text in the DOM.
    scripts = page.locator('.row[data-path="src/treestamp"] .name')
    if scripts.get_attribute("aria-expanded") == "false":
        scripts.click()
    visible(page, '.row[data-path^="src/treestamp/"]')
    rows = page.locator("#rows .row.leaf")
    index = rows.evaluate_all(
        "rows => rows.map((r,i)=>[i,r.querySelector('.name').textContent.length])"
        ".sort((a,b)=>b[1]-a[1])[0][0]"
    )
    rows.nth(index).focus()
    page.locator("#row-note").click()
    visible(page, "#note-dialog")


def show_settings(page: Page) -> None:
    if page.locator("#note-dialog").is_visible():
        page.locator("#note-cancel").click()
    if page.locator(".settings-open").is_visible():
        page.locator(".settings-open").click()
    visible(page, "#settings")


def show_reset(page: Page) -> None:
    page.locator("#reset-tree").click()
    visible(page, "#reset-dialog")


def show_markdown(page: Page) -> None:
    if page.locator("#reset-dialog").is_visible():
        page.locator("#reset-cancel").click()
    if page.locator("#settings:popover-open").count():
        page.locator('#settings [popovertargetaction="hide"]').click()
    page.locator("#tab-stamp").click()
    visible(page, "#stamp-panel")


def show_info(page: Page) -> None:
    page.locator("#tab-info").click()
    visible(page, "#info-panel")


def show_return(page: Page) -> None:
    page.locator(".wordmark").click()
    visible(page, "#entry-return-welcome")


def show_picker(page: Page, repo: str) -> None:
    page.locator("#entry-url").fill(repo)
    page.locator("#entry-browse").click()
    visible(page, ".source-row")
    for name in ("src", "docs"):
        row = page.locator(f'.source-row[data-path="{name}"]')
        if row.count() and row.get_attribute("aria-expanded") == "false":
            row.click()


def select_document(page: Page) -> None:
    page.locator('.source-row[data-path="README.md"] .source-name').click()
    visible(page, "#reload")


def show_load_error(page: Page) -> None:
    """A deterministic service failure, confined to this browser context."""
    pattern = "**/api/preview*"
    page.route(
        pattern,
        lambda route: route.fulfill(
            status=503,
            json={
                "error": {
                    "code": "upstream_unavailable",
                    "message": "Could not load this file.",
                }
            },
        ),
    )
    try:
        page.locator("#reload").click()
        visible(page, "#reload-error")
    finally:
        page.unroute(pattern)


def show_placement_choice(page: Page) -> None:
    page.locator("#reload").click()
    visible(page, "#placement-choice")


def show_placement_tree(page: Page) -> None:
    page.locator("#placement-start").click()
    visible(page, "#placement-work")


def show_expired_draft(page: Page, url: str) -> None:
    """Restore the saved example against an unavailable snapshot."""
    pattern = "**/api/op"
    page.route(
        pattern,
        lambda route: route.fulfill(
            status=410,
            json={
                "error": {
                    "code": "snapshot_unavailable",
                    "message": "Saved tree unavailable.",
                }
            },
        ),
    )
    try:
        page.goto(url, wait_until="domcontentloaded")
        visible(page, "#entry-return-welcome")
        page.locator("#entry-return-welcome").click()
        visible(page, "#entry-error")
    finally:
        page.unroute(pattern)


def capture_profile(
    browser: Browser,
    args: argparse.Namespace,
    profile: tuple[str, int, int, str],
    deadline: float,
) -> tuple[list[Capture], list[str]]:
    name, width, height, theme = profile
    context = browser.new_context(
        viewport={"width": width, "height": height},
        color_scheme=theme,
        reduced_motion="reduce",
    )
    page = context.new_page()
    page.set_default_timeout(1500)
    page.set_default_navigation_timeout(5000)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(f"{name}: {error}"))
    gallery = Gallery(page, name, args.output, deadline)
    actions = [
        ("welcome", lambda: show_welcome(page, args.url)),
        ("editor", lambda: open_example(page)),
        ("note", lambda: open_note(page)),
        ("settings", lambda: show_settings(page)),
        ("discard", lambda: show_reset(page)),
        ("markdown", lambda: show_markdown(page)),
        ("info", lambda: show_info(page)),
        ("returning-entry", lambda: show_return(page)),
        ("picker-folder", lambda: show_picker(page, args.repo)),
        ("picker-file", lambda: select_document(page)),
        ("failed-load", lambda: show_load_error(page)),
        ("placement-invitation", lambda: show_placement_choice(page)),
        ("placement-tree", lambda: show_placement_tree(page)),
        ("expired-draft", lambda: show_expired_draft(page, args.url)),
    ]
    # Register filenames before capture so interrupted runs can also be cleaned.
    metadata = json.loads(args.output.joinpath("manifest.json").read_text())
    metadata["captures"].extend(
        {"image": f"{name}-{state}.png"} for state, _ in actions
    )
    write_manifest(args.output, metadata)
    try:
        for state, action in actions:
            gallery.take(state, action)
    finally:
        context.close()
    return gallery.captures, errors


def git_output(*arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    return result.stdout.strip()


def card(capture: Capture) -> str:
    title = html.escape(capture.state.replace("-", " "))
    if capture.image:
        image = html.escape(capture.image, quote=True)
        content = f'<a href="{image}"><img src="{image}" alt="{title}"></a>'
    else:
        content = f'<p class="gap">Not reached: {html.escape(capture.detail)}</p>'
    return f"<article><h3>{title}</h3>{content}</article>"


def write_gallery(
    output: Path, captures: list[Capture], metadata: dict[str, Any]
) -> None:
    sections = []
    for name, width, height, theme in PROFILES:
        cards = "".join(card(c) for c in captures if c.profile == name)
        sections.append(
            f'<section id="{name}"><h2>{name} · {width}×{height} · {theme}</h2>'
            f'<div class="grid">{cards}</div></section>'
        )
    styles = """
        body{margin:24px;background:#eee;color:#222;font:16px system-ui}
        h1{font-size:24px}h2{font-size:20px}h3{font-size:16px;margin:0;padding:8px}
        section{width:1080px;max-width:100%;margin:32px 0;padding:16px;
        box-sizing:border-box;background:#fff}
        .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}
        article{border:1px solid #ccc;min-width:0;align-self:start}
        img{display:block;width:100%;height:auto}
        .gap{padding:12px;color:#a00;overflow-wrap:anywhere}
        a{color:inherit}p{max-width:85ch}
        .meta{font:14px monospace;overflow-wrap:anywhere}
    """
    heading = (
        "<h1>UI screenshot sweep</h1><p>Capture success is not a visual review. "
        "Check spacing, typography, color, readability, balance, consistency, "
        "and action hierarchy. Open an image for full size.</p>"
        f'<p class="meta">Commit {html.escape(metadata["commit"])} · '
        f"{html.escape(metadata['created_at'])} · "
        f"{metadata['elapsed_seconds']} seconds</p>"
        "<p>Failed-load and expired-draft use injected service errors. "
        "Placement requires a stale README fixture. "
        "Missing states are gaps, never passes.</p>"
    )
    output.joinpath("index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>UI screenshot sweep</title>"
        f"<style>{styles}</style>{heading}{''.join(sections)}</html>"
    )


def make_contact_sheets(browser: Browser, output: Path) -> None:
    page = browser.new_page(viewport={"width": 1140, "height": 900})
    try:
        page.goto(output.joinpath("index.html").as_uri())
        page.locator("img").evaluate_all(
            "images => Promise.all(images.map(image => image.decode()))"
        )
        for name, _, _, _ in PROFILES:
            page.locator(f"#{name}").screenshot(
                path=output / f"contact-{name}.png", animations="disabled"
            )
    finally:
        page.close()


def write_manifest(output: Path, metadata: dict[str, Any]) -> None:
    output.joinpath("manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")


def export_gallery(
    browser: Browser,
    output: Path,
    captures: list[Capture],
    metadata: dict[str, Any],
    started: float,
) -> None:
    # Replace the previous run's manifest before attempting optional exports.
    metadata.update(export_status="pending", export_error="")
    write_manifest(output, metadata)
    try:
        output.joinpath("index.html").unlink(missing_ok=True)
        for name, _, _, _ in PROFILES:
            output.joinpath(f"contact-{name}.png").unlink(missing_ok=True)
        write_gallery(output, captures, metadata)
        make_contact_sheets(browser, output)
        metadata["export_status"] = "complete"
    except Exception as exc:
        metadata["export_status"] = "failed"
        metadata["export_error"] = str(exc)[:600]
    finally:
        metadata["elapsed_seconds"] = round(time.monotonic() - started, 1)
        write_manifest(output, metadata)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--repo", default="fixture/repo")
    parser.add_argument("--output", type=Path, default=ROOT / "output/ui-review")
    parser.add_argument(
        "--clean", action="store_true", help="Remove this gallery's artifacts"
    )
    parser.add_argument(
        "--browser",
        default="chrome",
        help="Playwright browser channel; use chromium for its bundled browser",
    )
    args = parser.parse_args()
    args.output = args.output.resolve()
    return args


def clean_gallery(output: Path) -> None:
    manifest = output / "manifest.json"
    if not manifest.is_file():
        return
    metadata = json.loads(manifest.read_text())
    names = {"index.html", "manifest.json"}
    names.update(capture.get("image", "") for capture in metadata["captures"])
    names.update(f"contact-{profile['name']}.png" for profile in metadata["profiles"])
    for name in names:
        # Only direct files recorded by this gallery; never traverse supplied paths.
        if name and Path(name).name == name and name not in {".", ".."}:
            path = output / name
            if path.is_file() or path.is_symlink():
                path.unlink()
    if not any(output.iterdir()):
        output.rmdir()


def main() -> int:
    args = arguments()
    if args.clean:
        clean_gallery(args.output)
        print(f"Removed recorded gallery artifacts: {args.output}")
        return 0
    clean_gallery(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    write_manifest(
        args.output,
        {
            "export_status": "pending",
            "captures": [],
            "profiles": [{"name": name} for name, _, _, _ in PROFILES],
        },
    )
    started = time.monotonic()
    captures: list[Capture] = []
    errors: list[str] = []
    with sync_playwright() as playwright:
        channel = None if args.browser == "chromium" else args.browser
        browser = playwright.chromium.launch(channel=channel)
        try:
            for profile in PROFILES:
                results, page_errors = capture_profile(
                    browser, args, profile, started + 50
                )
                captures.extend(results)
                errors.extend(page_errors)
            metadata = {
                "created_at": datetime.now(UTC).isoformat(),
                "commit": git_output("rev-parse", "HEAD"),
                "working_tree": git_output("status", "--short"),
                "url": args.url,
                "repo": args.repo,
                "elapsed_seconds": round(time.monotonic() - started, 1),
                "profiles": [
                    {"name": name, "width": width, "height": height, "theme": theme}
                    for name, width, height, theme in PROFILES
                ],
                "browser_errors": errors,
                "captures": [asdict(capture) for capture in captures],
            }
            export_gallery(browser, args.output, captures, metadata, started)
        finally:
            browser.close()
    captured = sum(c.status == "captured" for c in captures)
    print(
        f"Captured {captured}/{len(captures)} states in "
        f"{metadata['elapsed_seconds']}s: {args.output / 'index.html'}"
    )
    print("Review required; capture completion is not a visual pass.")
    if metadata["export_error"]:
        print(f"Gallery export failed: {metadata['export_error']}")
    complete = captured == len(captures) and not errors
    return 0 if complete and metadata["export_status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
