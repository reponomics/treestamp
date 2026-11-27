"""Source containers do not determine hosted editing or model change detection."""

from copy import deepcopy
from dataclasses import replace

import pytest

from treestamp.document import render_region
from treestamp.svg import parse_svg
from treestamp.svg_layout import LAYOUT_STYLES
from treestamp_web.localgit import FakeGitHub, LocalRepository
from treestamp_web.svg_work import SvgBusyError, SvgWorkPool

from .conftest import Repo
from .test_preview import op, preview, service_for
from .test_svg import svg_source


def paired_sources(repo: Repo) -> FakeGitHub:
    repo.write("README.md")
    _, original = svg_source(repo)
    repo.write("README.md", render_region(parse_svg(original).document))
    repo.commit("same decoded document in both containers")
    return FakeGitHub(LocalRepository(repo.path))


def forbid_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    def render(*args: object) -> None:
        pytest.fail("editing must not generate SVG layout")

    async def unavailable(*args: object) -> None:
        raise SvgBusyError()

    monkeypatch.setitem(LAYOUT_STYLES, "continuous", render)
    monkeypatch.setattr(SvgWorkPool, "run", unavailable)


def test_equivalent_source_models_edit_and_reset_without_rendering(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = paired_sources(repo)
    forbid_rendering(monkeypatch)
    service, _ = service_for(fake)
    markdown = preview(service, document="README.md")
    svg = preview(service, document="assets/tree.svg")
    assert not markdown.dirty and not svg.dirty
    assert markdown.tree == svg.tree and markdown.settings == svg.settings
    for action, path, text in (
        ("annotate", "src/main.py", "new note"),
        ("hide", "src/main.py", ""),
        ("collapse", "src", ""),
        ("reset", "", ""),
    ):
        markdown = op(service, markdown, action, path, text)
        svg = op(service, svg, action, path, text)
        assert markdown.dirty == svg.dirty == (action != "reset")
        assert markdown.tree == svg.tree
        assert markdown.state["curation"] == svg.state["curation"]
    assert not svg.dirty


def test_reconciliation_changes_and_discard_are_container_independent(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = paired_sources(repo)
    repo.write("src/new.py")
    repo.commit("repository advances")
    forbid_rendering(monkeypatch)
    service, _ = service_for(fake)
    for source in ("README.md", "assets/tree.svg"):
        opened = preview(service, document=source)
        assert opened.dirty and "new.py" in opened.tree
        edited = op(service, opened, "annotate", "src/main.py", "new note")
        reset = op(service, edited, "reset")
        assert reset.tree == opened.tree and reset.dirty
        assert reset.state["curation"] == opened.state["curation"]


def test_svg_appearance_is_not_a_treestamp_edit(repo: Repo) -> None:
    fake = paired_sources(repo)
    service, _ = service_for(fake)
    opened = preview(service, document="assets/tree.svg")
    state = deepcopy(opened.state)
    state["svg_appearance"]["theme"] = "light"
    presented = op(service, replace(opened, state=state), "present")
    assert not presented.dirty
    assert presented.tree == opened.tree
    assert presented.state["curation"] == opened.state["curation"]
