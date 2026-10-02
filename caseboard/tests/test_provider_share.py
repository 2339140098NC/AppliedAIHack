"""The provider screen is a packet the firm can hold back and send."""

from pathlib import Path

from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic_settings import SettingsConfigDict

from caseboard.config import Settings
from caseboard.domain.enums import DocType, EventKind, SegmentKind, Sensitivity
from caseboard.domain.models import Evidence, Facet, ProviderShare, Segment, TimelineEvent
from caseboard.main import create_app
from caseboard.share.packet import load_share
from caseboard.store.documents import DocumentStore
from caseboard.web.workspace.board import Workspace
from caseboard.web.workspace.query import WorkspaceQuery

TEMPLATES = Path(__file__).resolve().parents[1] / "caseboard" / "web" / "templates"


class IsolatedSettings(Settings):
    """Ignore the developer .env so a test cannot write the shared store."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")


def _query(**changes: str) -> WorkspaceQuery:
    data = {
        "view": "provider",
        "provider": "montefiore",
        "tab": "timeline",
        "document": "",
        "page": 0,
        "quote": "",
        "ev": "",
        "selected": "",
        "drawer": "",
        "panel": "",
    }
    data.update(changes)
    return WorkspaceQuery(
        view=str(data["view"]),
        provider=str(data["provider"]),
        tab=str(data["tab"]),
        document=str(data["document"]),
        page=int(data["page"] or 0),
        quote=str(data["quote"]),
        ev=str(data["ev"]),
        selected=str(data["selected"]),
        drawer=str(data["drawer"]),
        panel=str(data["panel"]),
    )


def _seed(store: DocumentStore) -> None:
    store.put(
        DocType.timeline_event,
        "visit",
        TimelineEvent(
            id="visit",
            date="2023-04-24",
            label="Seen at Montefiore",
            kind=EventKind.treatment,
            sensitivity=Sensitivity.provider_visible,
            sensitivity_reason="Treating clinical fact",
            origin="pdf",
            evidence=[Evidence(document="montefiore-visit.pdf", page=1, quote="Arrival")],
        ),
    )
    store.put(
        DocType.facet,
        "knee",
        Facet(
            id="knee",
            facet_key="injury.right_knee",
            value="contusion",
            sensitivity=Sensitivity.provider_visible,
            sensitivity_reason="Treating clinical fact",
            authored_by="Montefiore Nyack",
            segment_kind=SegmentKind.clinical_note,
            evidence=[Evidence(document="montefiore-visit.pdf", page=1, quote="contusion")],
        ),
    )
    store.put(
        DocType.segment,
        "note",
        Segment(
            id="note",
            source_file="montefiore-visit.pdf",
            page_start=1,
            page_end=2,
            kind=SegmentKind.clinical_note,
            facility="Montefiore Nyack Hospital",
        ),
    )


def _render(name: str, context: dict) -> str:
    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    return env.get_template(name).render(**context)


def test_hyphenated_chart_and_its_exams_stay_on_the_provider_timeline(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    filename = "04-medical-records__created__new-horizon-surgical-center-records.pdf"
    store.put(
        DocType.segment,
        "op",
        Segment(
            id="op",
            source_file=filename,
            page_start=1,
            page_end=4,
            kind=SegmentKind.operative_report,
            facility="New Horizon Surgical Center, LLC",
        ),
    )
    store.put(
        DocType.timeline_event,
        "visit",
        TimelineEvent(
            id="visit",
            date="2023-07-26",
            label="Right shoulder arthroscopy",
            kind=EventKind.surgery,
            sensitivity=Sensitivity.provider_visible,
            sensitivity_reason="Clinical or accident event",
            origin="pdf",
            evidence=[Evidence(document=filename, page=2, quote="Arthroscopy")],
        ),
    )
    store.put(
        DocType.timeline_event,
        "exam",
        TimelineEvent(
            id="exam",
            date="2024-01-09",
            label="Follow-up examination",
            kind=EventKind.exam,
            sensitivity=Sensitivity.firm_only,
            sensitivity_reason="Firm event",
            origin="pdf",
            evidence=[Evidence(document=filename, page=3, quote="Follow-up")],
        ),
    )
    years = Workspace(store, _query(provider="newhorizon")).context()["years"]
    labels = [event["label"] for year in years for event in year["events"]]
    assert labels == ["Follow-up examination", "Right shoulder arthroscopy"]
    assert Workspace(store, _query(provider="montefiore")).context()["years"] == []


def test_firm_timeline_has_no_packet_controls(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    _seed(store)
    firm = Workspace(store, _query(view="firm")).context()
    provider = Workspace(store, _query()).context()
    assert firm["share"] is None
    assert "include-form" not in _render("partials/timeline.html", firm)
    page = _render("partials/timeline.html", provider)
    assert "Packet for" in _render("partials/stage.html", provider)
    form_at = page.find("include-form")
    assert form_at > 0
    assert "hx-get" not in page[page.rfind("<div class=\"flex flex-wrap", 0, form_at):form_at]
    assert provider["share"]["included"] == 3
    assert provider["share"]["held"] == 0


def test_hold_back_and_send_keep_the_rest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)
    settings = IsolatedSettings(
        upstash_redis_rest_url="",
        upstash_redis_rest_token="",
        db_path=tmp_path / "case.sqlite",
        gemini_api_key="",
        clio_client_id="",
        clio_client_secret="",
    )
    app = create_app(settings)
    _seed(app.state.store)
    client = TestClient(app)
    query = "?view=provider&provider=montefiore&tab=timeline"
    held = client.post(f"/share/toggle{query}", data={"record_id": "visit"})
    assert held.status_code == 200
    assert "Held" in held.text
    assert "2 included" in held.text
    packet = load_share(app.state.store, "montefiore")
    assert packet.excluded == ["visit"]
    sent = client.post(f"/share/send{query}")
    assert sent.status_code == 200
    assert "Send update" not in sent.text
    saved = ProviderShare.model_validate(app.state.store.list_type(DocType.share)[0])
    assert saved.sent_ids == ["knee", "note"]
    assert "visit" not in saved.sent_ids
    firm = client.get("/")
    assert 'class="include-form' not in firm.text
    assert "Packet for" not in firm.text
