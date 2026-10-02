"""Timeline rows use a stored lawyer's reading when one exists."""

from pathlib import Path

from caseboard.domain.enums import DocType, EventKind, Sensitivity
from caseboard.domain.models import Evidence, ItemGlance, TimelineEvent
from caseboard.glance.text import glance_key
from caseboard.store.documents import DocumentStore
from caseboard.web.workspace.board import Workspace
from caseboard.web.workspace.query import WorkspaceQuery


def test_urgent_reading_replaces_the_label_and_reaches_the_summary(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    event = TimelineEvent(
        id="visit",
        date="2023-05-08",
        label="Email",
        kind=EventKind.email,
        sensitivity=Sensitivity.firm_only,
        sensitivity_reason="Clio communication",
        origin="clio",
        evidence=[Evidence(document="clio:9", page=1, quote="Benefits exhausted")],
    )
    store.put(DocType.timeline_event, event.id, event)
    reading = ItemGlance(id=glance_key(event), category="Insurance", line="No-fault benefits exhausted", urgent=True)
    store.put(DocType.glance, reading.id, reading)
    context = Workspace(store, _query()).context()
    shown = context["years"][0]["events"][0]
    assert shown["kind"] == "Insurance"
    assert shown["form"] == "Email"
    assert shown["label"] == "No-fault benefits exhausted"
    assert shown["urgent"] is True
    assert shown["tone"] == "insurance"
    assert context["urgent"][0]["line"] == "No-fault benefits exhausted"
    assert context["urgent"][0]["category"] == "Insurance"
    assert context["urgent"][0]["when"] == "May 8, 2023"


def _query() -> WorkspaceQuery:
    return WorkspaceQuery(
        view="firm",
        provider="montefiore",
        tab="timeline",
        document="",
        page=0,
        quote="",
        ev="",
        selected="",
        drawer="",
    )
