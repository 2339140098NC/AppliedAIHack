"""Clio notes, emails, and calls open as text, not as a PDF page."""

from pathlib import Path

from caseboard.domain.enums import CommSource, DocType, Sensitivity
from caseboard.domain.models import Communication
from caseboard.store.documents import DocumentStore
from caseboard.web.workspace.board import Workspace
from caseboard.web.workspace.query import WorkspaceQuery


def _query(**changes: str) -> WorkspaceQuery:
    data = {
        "view": "firm",
        "provider": "montefiore",
        "tab": "timeline",
        "document": "clio:99",
        "page": 1,
        "quote": "",
        "ev": "",
        "selected": "",
        "drawer": "1",
    }
    data.update(changes)
    return WorkspaceQuery(
        view=str(data["view"]),
        provider=str(data["provider"]),
        tab=str(data["tab"]),
        document=str(data["document"]),
        page=int(data["page"]),
        quote=str(data["quote"]),
        ev=str(data["ev"]),
        selected=str(data["selected"]),
        drawer=str(data["drawer"]),
    )


def test_note_body_opens_in_the_drawer(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    store.put(
        DocType.communication,
        "note-1",
        Communication(
            id="note-1",
            clio_id="99",
            source=CommSource.note,
            subject="Discovery is stuck",
            body="Stuck on the maintenance records.",
            occurred_on="2024-09-06",
            sensitivity=Sensitivity.firm_only,
        ),
    )
    viewer = Workspace(store, _query()).context()["viewer"]
    assert viewer["record"] is True
    assert viewer["image"] is False
    assert viewer["title"] == "Discovery is stuck"
    assert viewer["body"] == "Stuck on the maintenance records."
    assert "Note" in viewer["sub"]


def test_provider_view_does_not_open_a_clio_record(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    store.put(
        DocType.communication,
        "note-1",
        Communication(
            id="note-1",
            clio_id="99",
            source=CommSource.phone,
            subject="Call",
            body="Transcript of the call.",
            sensitivity=Sensitivity.firm_only,
        ),
    )
    viewer = Workspace(store, _query(view="provider")).context()["viewer"]
    assert viewer["record"] is False
    assert "Transcript" not in viewer["body"]
