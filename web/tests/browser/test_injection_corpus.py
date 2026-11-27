"""Markup in names, notes, errors, and links stays literal text on every surface.

A small fixed corpus, not a fuzzer: HTML, SVG, and event-handler payloads are
committed as paths and notes in their own fixture repository, served through
the local service and fake GitHub. Each journey checks for literal text and
for the absence of attacker-created elements and attributes, executed
sentinels, dialogs, unexpected requests, and navigation. Rendering journeys
also run with the Content Security Policy bypassed in the test browser, so
safe rendering does not depend on that header.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote, urlsplit

import pytest

from .conftest import Fixture, _git, service

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import Browser, Page, Request, Route, expect  # noqa: E402

pytestmark = pytest.mark.browser

IMG = '<img src=x onerror="window.__xss=1">'
SVG = "<svg onload=window.__xss=2>"
SCRIPT = "<script>window.__xss=3</script>"
ATTRIBUTE = '"><b onmouseover=window.__xss=4>x'
SCRIPT_URL = "javascript:window.__xss=5"
KEEP = "keep <b>.py"
MOVED = f"{SVG}.py"

OLD_PATHS = (f"{IMG}.md", f"{SVG}/inner.txt", f"{ATTRIBUTE}.txt", SCRIPT_URL, KEEP)
NOTES = {
    "": f"see {SCRIPT_URL}",
    f"{IMG}.md": SCRIPT,
    KEEP: f"existing {IMG}",
    f"old/{MOVED}": f"moved {ATTRIBUTE}",
}

# Attacker-created attributes or elements; the page's own markup has none.
FOREIGN_MARKUP = """() => [...document.querySelectorAll("*")].flatMap((node) => [
  ...[...node.attributes]
    .filter((a) => /^on/i.test(a.name)
      || (/^(href|src|action|formaction|xlink:href)$/i.test(a.name) && /^\\s*javascript:/i.test(a.value)))
    .map((a) => `${node.tagName}[${a.name}]`),
  ...(node.matches('img[src="x"], script:not([src])') ? [node.tagName] : []),
])"""


def _index(path: Path, entries: dict[str, bytes]) -> None:
    lines = b""
    for name, content in entries.items():
        oid = subprocess.run(
            ["git", "-C", str(path), "hash-object", "-w", "--stdin"],
            input=content,
            capture_output=True,
            check=True,
        ).stdout.strip()
        lines += b"100644 " + oid + b"\t" + name.encode("utf-8") + b"\0"
    subprocess.run(
        ["git", "-C", str(path), "update-index", "-z", "--add", "--index-info"],
        input=lines,
        check=True,
    )


def build_corpus_fixture(path: Path) -> Fixture:
    """Payload paths exist only in Git; filesystems cannot hold every such name."""
    from treestamp.document import Document, render_region
    from treestamp.model import Entry, Settings, build_tree
    from treestamp.session import TreeSession

    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    _git(path, "config", "user.email", "test@example.invalid")
    _git(path, "config", "user.name", "Test")
    old = [*OLD_PATHS, f"old/{MOVED}", "README.md"]
    session = TreeSession(build_tree(Entry(name) for name in old), Settings())
    for node in session.root.walk():
        if node.is_dir:
            session.expand(node.path)
    for name, note in NOTES.items():
        session.set_annotation(name, note)
    session.hide("README.md")
    region = render_region(
        Document(session.printed_tree(), Settings(), session.saved_hidden())
    )
    (path / "README.md").write_text(f"# Corpus\n\n{region}", encoding="utf-8")
    _git(path, "add", "README.md")
    _index(path, {name: b"x" for name in [*OLD_PATHS, f"old/{MOVED}"]})
    _git(path, "commit", "-q", "-m", "Document payloads")
    previous = _git(path, "rev-parse", "HEAD")
    _git(path, "update-index", "--force-remove", f"old/{MOVED}")
    _index(path, {f"new/{MOVED}": b"x"})
    _git(path, "commit", "-q", "-m", "Move one annotated entry")
    return Fixture(path, previous, _git(path, "rev-parse", "HEAD"))


@pytest.fixture(scope="session")
def corpus_service(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    fixture = build_corpus_fixture(tmp_path_factory.mktemp("corpus") / "repo")
    yield from service.__wrapped__(fixture)


class Guard:
    """Record evidence of script execution, dialogs, stray requests, and errors."""

    def __init__(self, page: Page, base: str) -> None:
        self.page, self.base = page, base
        self.errors: list[str] = []
        self.dialogs: list[str] = []
        self.stray: list[str] = []
        page.on("pageerror", lambda error: self.errors.append(str(error)))
        page.on("dialog", self._dialog)
        page.on("request", self._request)

    def _dialog(self, dialog: object) -> None:
        self.dialogs.append(dialog.message)  # type: ignore[attr-defined]
        dialog.dismiss()  # type: ignore[attr-defined]

    def _request(self, request: Request) -> None:
        url = urlsplit(request.url)
        if url.scheme in ("data", "blob") or request.resource_type == "document":
            return
        same_origin = request.url.startswith(self.base + "/")
        expected = (
            url.path.startswith(("/api/", "/static/")) or url.path == "/favicon.ico"
        )
        if not (same_origin and expected):
            self.stray.append(request.url)

    def check(self) -> None:
        assert self.page.evaluate("window.__xss") is None, "a payload executed"
        assert self.page.evaluate(FOREIGN_MARKUP) == []
        assert (self.dialogs, self.stray, self.errors) == ([], [], [])
        assert self.page.url.startswith(self.base + "/"), "the page navigated away"


@pytest.fixture(params=[False, True], ids=["csp", "csp-bypassed"])
def corpus_page(request: pytest.FixtureRequest, browser: Browser) -> Iterator[Page]:
    context = browser.new_context(bypass_csp=request.param)
    yield context.new_page()
    context.close()


def test_editor_placement_and_markdown_render_payloads_as_text(
    corpus_page: Page, corpus_service: str
) -> None:
    page, guard = corpus_page, Guard(corpus_page, corpus_service)
    page.goto(f"{corpus_service}/fixture/repo?root=.&document=README.md")
    expect(page.locator("#placement-dialog")).to_be_visible()
    expect(page.locator("#placement-source")).to_have_text("old/")
    page.keyboard.press("s")  # skip the folder; its annotated entry follows
    expect(page.locator("#placement-source")).to_have_text(MOVED)
    expect(page.locator("#placement-note")).to_contain_text(f"moved {ATTRIBUTE}")
    page.locator(f'#placement-rows [data-path="{KEEP}"]').click()
    page.keyboard.press("Enter")
    expect(page.locator("#placement-replace-question")).to_contain_text(KEEP)
    page.locator("#placement-replace-accept").click()
    expect(page.locator("#placement-dialog")).to_be_hidden()
    rows, region = page.locator("#rows"), page.locator("#region")
    for text in (f"{IMG}.md", f"{SVG}/", f"{ATTRIBUTE}.txt", SCRIPT_URL, SCRIPT):
        expect(rows).to_contain_text(text)
    for text in (f"{IMG}.md", SCRIPT, f"moved {ATTRIBUTE}", f"see {SCRIPT_URL}"):
        expect(region).to_contain_text(text)
    guard.check()


def test_source_browser_lists_payload_names_as_text(
    corpus_page: Page, corpus_service: str
) -> None:
    page, guard = corpus_page, Guard(corpus_page, corpus_service)
    page.goto(corpus_service + "/")
    page.locator("#entry-url").fill("fixture/repo")
    page.locator("#entry-browse").click()
    browser = page.locator("#source-browser")
    for name in (f"{IMG}.md", f"{SVG}/", f"{ATTRIBUTE}.txt", SCRIPT_URL, KEEP):
        expect(browser).to_contain_text(name)
    page.locator(f'#source-browser [data-path="{SVG}"]').click()
    expect(browser).to_contain_text("inner.txt")
    guard.check()


@pytest.mark.parametrize(
    ("query", "shown"),
    [
        (f"root={quote(f'missing {SVG}')}&document=", f"missing {SVG}"),
        (f"document={quote(IMG)}.md", f"{IMG}.md"),
    ],
    ids=["root", "document"],
)
def test_query_errors_render_payloads_as_text(
    corpus_page: Page, corpus_service: str, query: str, shown: str
) -> None:
    page, guard = corpus_page, Guard(corpus_page, corpus_service)
    page.goto(f"{corpus_service}/fixture/repo?{query}")
    expect(page.locator("#error-message")).to_contain_text(shown)
    guard.check()


def test_script_scheme_input_and_routes_do_not_navigate(
    page: Page, corpus_service: str
) -> None:
    guard = Guard(page, corpus_service)
    page.goto(corpus_service + "/")
    page.locator("#entry-url").fill(SCRIPT_URL)
    page.locator("#entry-create").click()
    expect(page.locator("#entry-error")).to_be_visible()
    guard.check()
    page.goto(f"{corpus_service}/{quote(SCRIPT_URL)}/x")
    alert = page.get_by_role("alert").filter(has_text="not a valid GitHub owner")
    expect(alert).to_be_visible()
    guard.check()


def test_synthetic_repository_link_cannot_become_a_script_url(
    page: Page, corpus_service: str
) -> None:
    # Synthetic: the service builds this link from validated identifiers, so a
    # forged response is an input to the page, not demonstrated reachability.
    def forge(route: Route) -> None:
        response = route.fetch()
        data = response.json()
        data["repository"]["url"] = SCRIPT_URL
        route.fulfill(response=response, json=data)

    guard = Guard(page, corpus_service)
    page.route("**/api/preview*", forge)
    page.goto(f"{corpus_service}/fixture/repo?root=.")
    expect(page.locator("#error-message")).to_contain_text("could not display")
    expect(page.locator("#error-hint")).to_contain_text("previous tree is unchanged")
    assert page.locator("#visit-repo").get_attribute("href") != SCRIPT_URL
    guard.check()


def test_sentinels_detect_execution_when_csp_is_bypassed(
    browser: Browser, corpus_service: str
) -> None:
    """Control: the checks above would notice a payload that did run."""
    context = browser.new_context(bypass_csp=True)
    page = context.new_page()
    guard = Guard(page, corpus_service)
    page.goto(corpus_service + "/")
    page.evaluate("html => document.body.insertAdjacentHTML('beforeend', html)", IMG)
    page.wait_for_function("window.__xss === 1")
    with pytest.raises(AssertionError):
        guard.check()
    assert guard.stray and page.evaluate(FOREIGN_MARKUP)
    context.close()
