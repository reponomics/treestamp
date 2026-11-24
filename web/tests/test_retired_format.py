"""Retired list documents and states fail without replacing accepted work."""

from copy import deepcopy

import pytest

from treestamp_web.preview import PreviewError

from .test_preview import op, preview, service_for


@pytest.mark.parametrize("rows", ["./\n", "./\n- literal \\[gitlink\\]\n"])
def test_legacy_list_document_is_explicitly_rejected(fake, repo, rows):
    content = "<!-- treestamp:start -->\n" + rows + "<!-- treestamp:end -->\n"
    repo.write("legacy.md", content)
    repo.commit("legacy list artifact")
    service, _ = service_for(fake)
    with pytest.raises(PreviewError, match="list") as error:
        preview(service, document="legacy.md")
    assert error.value.code == "curation"
    assert (repo.path / "legacy.md").read_text() == content


def test_retired_list_state_cannot_replace_an_accepted_document(fake):
    service, _ = service_for(fake)
    accepted = preview(service, document="")
    candidate = deepcopy(accepted)
    candidate.state["curation"]["settings"]["style"] = "list"
    with pytest.raises(PreviewError):
        op(service, candidate, "restore")
    assert op(service, accepted, "restore").region == accepted.region
