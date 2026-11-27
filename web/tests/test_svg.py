"""Hosted SVG uses the same document projection and keeps drawings out of state."""

from __future__ import annotations

import base64
import json
from copy import deepcopy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from treestamp.document import Document, parse_document, render_region
from treestamp.gitio import capture_snapshot
from treestamp.model import Node, Settings
from treestamp.session import TreeSession
from treestamp.svg import SvgAppearance, parse_svg, render_svg, render_svg_variants
from treestamp_web.app import create_app
from treestamp_web.export import EXPORT_BODY_CAP
from treestamp_web.localgit import FakeGitHub, LocalRepository
from treestamp_web.preview import SVG_NOTICE, Envelope, PreviewError
from treestamp_web.routing import COOKIE

from .conftest import Clock, Repo, make_config, transport_for
from .test_examples import EXAMPLES
from .test_placement import placed, stale
from .test_preview import op, preview, service_for


def svg_source(
    repo: Repo, *, root: str = ".", theme: str = "dark"
) -> tuple[FakeGitHub, bytes]:
    repo.write("src/main.py")
    repo.write("src/private.py")
    repo.write("assets/tree.svg")
    repo.git("add", "-A")
    session = TreeSession(capture_snapshot(repo.path / root).tree, Settings(root=root))
    if root == ".":
        session.expand("src")
        session.hide("src/private.py")
    session.set_annotation("", "A repository")
    document = Document(
        session.printed_tree(), session.settings, session.saved_hidden()
    )
    content = render_svg(document, SvgAppearance(theme=theme)).encode()
    (repo.path / "assets/tree.svg").write_bytes(content)
    repo.commit()
    return FakeGitHub(LocalRepository(repo.path)), content


def export_body(region: str | None = None, **overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "region": region or render_region(Document(Node(".", "", "dir"))),
        "text_style": "unicode",
        "show_counts": True,
        "style": "continuous",
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("theme", ["adaptive", "light", "dark"])
def test_svg_load_is_clean_and_state_has_metadata_only(repo: Repo, theme: str) -> None:
    fake, original = svg_source(repo, theme=theme)
    service, client = service_for(fake)
    opened = preview(service, document="assets/tree.svg")
    assert opened.loaded and not opened.dirty
    assert opened.source_format == "svg"
    assert opened.svg_appearance == SvgAppearance(theme=theme)
    assert opened.notice == SVG_NOTICE
    baseline = base64.b64decode(opened.state["baseline"])
    assert (
        b"<metadata>" in baseline
        and b"<text " not in baseline
        and b"<line " not in baseline
    )
    assert len(baseline) < len(original)
    assert parse_svg(baseline).document == parse_svg(original).document
    assert "private.py" not in opened.tree
    calls = client.calls
    restored = op(service, opened, "restore")
    assert not restored.dirty and restored.state == opened.state
    assert client.calls == calls


def test_svg_baseline_is_normalized_and_appearance_can_be_recovered(repo: Repo) -> None:
    fake, original = svg_source(repo)
    service, _ = service_for(fake)
    opened = preview(service, document="assets/tree.svg")
    state = deepcopy(opened.state)
    state["baseline"] = base64.b64encode(original).decode()
    state.pop("svg_appearance")
    restored = Envelope.from_dict(state)
    assert restored.svg_appearance == opened.svg_appearance
    assert restored.baseline == base64.b64decode(opened.state["baseline"])


def test_svg_dirty_comparison_uses_decoded_baseline_without_original(
    repo: Repo,
) -> None:
    fake, _ = svg_source(repo)
    service, client = service_for(fake)
    opened = preview(service, document="assets/tree.svg")
    snapshot = service._snapshots.get(opened.repository.at(opened.commit))
    assert snapshot is not None
    snapshot.blobs.clear()
    calls = client.calls
    restored = op(service, opened, "restore")
    assert not restored.dirty
    assert op(service, restored, "annotate", "", "edited").dirty
    assert client.calls == calls


@pytest.mark.parametrize("theme", ["adaptive", "dark"])
def test_svg_annotation_and_appearance_reset_keep_source_baseline(
    repo: Repo, theme: str
) -> None:
    fake, original = svg_source(repo, theme=theme)
    service, _ = service_for(fake)
    opened = preview(service, document="assets/tree.svg")
    edited = op(service, opened, "annotate", "src/main.py", "Edited")
    assert edited.dirty and edited.state["baseline"] == opened.state["baseline"]
    edited.state["svg_appearance"]["theme"] = "light"
    presented = op(service, edited, "present")
    assert presented.dirty and presented.svg_appearance.theme == "light"
    reset = op(service, presented, "reset")
    assert not reset.dirty and reset.region == opened.region
    assert reset.svg_appearance.theme == theme
    assert reset.document == "assets/tree.svg"
    assert (repo.path / "assets/tree.svg").read_bytes() == original


def test_svg_manual_drawing_does_not_change_editor_state(
    repo: Repo,
) -> None:
    _, original = svg_source(repo)
    changed = original.replace(b"Repository tree", b"Manual drawing title")
    (repo.path / "assets/tree.svg").write_bytes(changed)
    repo.commit("drawing edit")
    fake = FakeGitHub(LocalRepository(repo.path))
    service, _ = service_for(fake)
    opened = preview(service, document="assets/tree.svg")
    assert not opened.dirty and "Manual drawing title" not in opened.region
    # Hosted export never writes; model the user replacing the downloaded file.
    downloaded = render_svg(
        parse_document(opened.region.encode()), opened.svg_appearance
    )
    repo.write("assets/tree.svg", downloaded)
    repo.commit("replace with exported artifact")
    service, _ = service_for(FakeGitHub(LocalRepository(repo.path)))
    assert not preview(service, document="assets/tree.svg").dirty


def test_unknown_svg_style_reports_fallback(repo: Repo) -> None:
    _, original = svg_source(repo)
    (repo.path / "assets/tree.svg").write_bytes(
        original.replace(b'style="continuous"', b'style="future"')
    )
    repo.commit("future style")
    service, _ = service_for(FakeGitHub(LocalRepository(repo.path)))
    opened = preview(service, document="assets/tree.svg")
    assert not opened.dirty and opened.svg_appearance.style == "continuous"
    assert "unavailable" in opened.warnings[0]


def test_svg_subtree_and_placement_use_embedded_document(
    repo: Repo, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = stale(repo)
    text = (repo.path / "README.md").read_bytes()
    repo.write("assets/tree.svg", render_svg(parse_document(text)))
    repo.commit("SVG source")

    def no_layout(*args: object) -> None:
        pytest.fail("note transfer must not render SVG")

    from treestamp.svg_layout import LAYOUT_STYLES

    monkeypatch.setitem(LAYOUT_STYLES, "continuous", no_layout)
    service, _ = service_for(fake)
    opened = preview(service, document="assets/tree.svg")
    assert opened.placement["remaining"] == 3
    transferred = placed(service, opened, [{"type": "place", "path": "new"}])
    assert transferred.placement["remaining"] == 1
    assert "First note" in transferred.region
    assert transferred.source_format == "svg"
    edited = op(service, transferred, "annotate", "", "temporary")
    discarded = op(service, edited, "reset")
    assert discarded.tree == transferred.tree and discarded.dirty
    assert discarded.state["baseline"] == opened.state["baseline"]


def test_svg_subtree_root_is_not_source_directory(repo: Repo) -> None:
    fake, _ = svg_source(repo, root="src")
    service, _ = service_for(fake)
    opened = preview(service, document="assets/tree.svg")
    assert opened.root == "src" and not opened.dirty


@pytest.mark.parametrize(
    "content",
    [
        b"<svg/>",
        b"not SVG",
        b'<svg xmlns="http://www.w3.org/2000/svg"/>',
        b'<!DOCTYPE svg [<!ENTITY x "x">]><svg/>',
    ],
)
def test_malformed_svg_is_rejected_without_new_session(
    repo: Repo, content: bytes
) -> None:
    fake, _ = svg_source(repo)
    service, _ = service_for(fake)
    accepted = preview(service, document="assets/tree.svg")
    before = deepcopy(accepted.state)
    (repo.path / "assets/tree.svg").write_bytes(content)
    repo.commit("malformed source")
    with pytest.raises(PreviewError) as error:
        preview(service, document="assets/tree.svg")
    assert error.value.status == 422
    assert accepted.state == before


@pytest.mark.parametrize(
    "appearance",
    [
        None,
        [],
        {},
        {"style": "unknown", "theme": "light"},
        {"style": "continuous", "theme": "pink"},
        {"style": [], "theme": "light"},
        {"style": "continuous", "theme": "light", "url": "https://example.com"},
    ],
)
def test_invalid_svg_appearance_does_not_change_state(
    repo: Repo, appearance: object
) -> None:
    fake, _ = svg_source(repo)
    service, _ = service_for(fake)
    opened = preview(service, document="assets/tree.svg")
    invalid = deepcopy(opened.state)
    invalid["svg_appearance"] = appearance
    with pytest.raises(PreviewError, match="appearance|style|theme"):
        op(service, replace(opened, state=invalid), "present")
    assert not op(service, opened, "restore").dirty


def test_svg_source_appearance_is_invalid_for_markdown_state(
    client: TestClient,
) -> None:
    state = client.get("/api/preview", params={"url": "o/r"}).json()["state"]
    state["svg_appearance"] = {"style": "continuous", "theme": "dark"}
    with pytest.raises(PreviewError, match="SVG baseline"):
        Envelope.from_dict(state)


def test_export_matches_core_without_session_or_source_change(
    client: TestClient,
) -> None:
    opened = client.get("/api/preview", params={"url": "o/r"}).json()
    before = deepcopy(opened)
    body = export_body(opened["region"])
    response = client.post("/api/export/svg", json=body)
    assert response.status_code == 200, response.text
    expected = render_svg_variants(parse_document(opened["region"].encode()))
    assert response.json() == {"variants": expected}
    assert response.headers["cache-control"] == "no-store"
    assert opened == before


@pytest.mark.parametrize("name", EXAMPLES)
def test_examples_export_without_acquiring_a_repository(
    client: TestClient, name: str
) -> None:
    example = EXAMPLES[name]
    calls = client.app.state.client.calls
    response = client.post(
        "/api/export/svg",
        json=export_body(
            example["region"],
            text_style=example["settings"]["style"],
            show_counts=example["settings"]["show_counts"],
        ),
    )
    assert response.status_code == 200, response.text
    assert parse_svg(
        response.json()["variants"]["adaptive"].encode()
    ).document == parse_document(example["region"].encode())
    assert client.app.state.client.calls == calls


@pytest.mark.parametrize(
    "change",
    [
        {"unexpected": True},
        {"appearance": None},
        {"style": None},
        {"style": "unknown"},
        {"style": ["continuous"]},
        {"region": 5},
        {"text_style": "list"},
        {"show_counts": 1},
        {"region": "unmarked"},
        {"region": "\ud800"},
        {"region": "x" * (256 * 1024 + 1)},
    ],
)
def test_export_rejects_invalid_fields(
    client: TestClient, change: dict[str, object]
) -> None:
    response = client.post("/api/export/svg", content=json.dumps(export_body(**change)))
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "invalid_export"


def test_export_rejects_prose_and_contradictory_preferences(client: TestClient) -> None:
    document = Document(
        Node(".", "", "dir", children=[Node("fold", "fold", "dir", files=2)])
    )
    region = render_region(document)
    for body in (
        export_body("Prose\n" + region),
        export_body(region, text_style="ascii"),
        export_body(region, show_counts=False),
    ):
        response = client.post("/api/export/svg", json=body)
        assert response.status_code == 422, response.text


def test_export_preserves_unobservable_text_preferences(client: TestClient) -> None:
    response = client.post(
        "/api/export/svg", json=export_body(text_style="ascii", show_counts=False)
    )
    artifact = parse_svg(response.json()["variants"]["adaptive"].encode())
    assert artifact.document.settings.style == "ascii"
    assert not artifact.document.settings.show_counts


def test_export_has_independent_body_bound_limiter_and_no_affinity(
    fake: FakeGitHub, clock: Clock
) -> None:
    config = make_config(
        max_state_bytes=64,
        svg_export_rate_limit_per_minute=2,
        fly_session_routing=True,
        fly_machine_id="a" * 14,
    )
    with TestClient(
        create_app(config, transport=transport_for(fake), clock=clock)
    ) as client:
        headers = {"Cookie": f"{COOKIE}={'b' * 14}"}
        for _ in range(2):
            response = client.post(
                "/api/export/svg", json=export_body(), headers=headers
            )
            assert response.status_code == 200, response.text
            assert "fly-replay" not in response.headers
        assert client.post("/api/export/svg", json=export_body()).status_code == 429
        clock.now += 60
        response = client.post("/api/export/svg", content=b" " * (EXPORT_BODY_CAP + 1))
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "export_too_large"
        response = client.post("/api/export/svg", content="not JSON")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_export"


def test_export_streaming_body_limit_without_content_length(client: TestClient) -> None:
    response = client.post(
        "/api/export/svg", content=iter([b" " * EXPORT_BODY_CAP, b" "])
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "export_too_large"


def test_export_rejects_excessively_nested_metadata(client: TestClient) -> None:
    region = render_region(Document(Node(".", "", "dir")))
    config = "<!-- treestamp:config\nhidden = " + "[" * 600 + "]" * 600 + "\n-->\n"
    region = region.replace("```", config + "```", 1)
    response = client.post("/api/export/svg", json=export_body(region))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_export"


def test_bundle_failure_returns_no_partial_artifacts(client, monkeypatch) -> None:
    from treestamp import svg
    from treestamp.svg_metadata import MAX_SVG_BYTES

    drawing = svg._drawing

    def oversized_dark(layout, appearance):
        return (
            " " * MAX_SVG_BYTES
            if appearance.theme == "dark"
            else drawing(layout, appearance)
        )

    monkeypatch.setattr(svg, "_drawing", oversized_dark)
    response = client.post("/api/export/svg", json=export_body())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_export"
    assert "variants" not in response.json()


def test_bundle_json_response_is_bounded(client, monkeypatch) -> None:
    from treestamp_web import app as app_module

    monkeypatch.setattr(app_module, "EXPORT_RESPONSE_CAP", 1)
    response = client.post("/api/export/svg", json=export_body())
    assert response.status_code == 422
    assert "response exceeds" in response.json()["error"]["message"]
    assert "variants" not in response.json()
