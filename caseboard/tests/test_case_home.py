"""Case status, critical stories, and the per-PDF extract panel."""

from datetime import date
from pathlib import Path

from caseboard.domain.enums import DocType, EventKind, SegmentKind, Sensitivity
from caseboard.domain.models import CaseSummary, Evidence, Facet, Segment, SourceFile, TimelineEvent
from caseboard.store.documents import DocumentStore
from caseboard.validate.checks import run_checks
from caseboard.validate.runner import ValidationRunner
from caseboard.web.workspace.board import Workspace
from caseboard.web.workspace.status_bar import case_age
from caseboard.web.workspace.query import WorkspaceQuery


def _facet(facet_id: str, key: str, value: str | None, document: str, *, kind: SegmentKind = SegmentKind.pleading) -> Facet:
    sensitivity = Sensitivity.firm_only if kind not in {SegmentKind.clinical_note, SegmentKind.bill} else Sensitivity.provider_visible
    return Facet(
        id=facet_id,
        facet_key=key,
        value=value,
        redacted=value is None,
        sensitivity=sensitivity,
        sensitivity_reason="test",
        segment_kind=kind,
        evidence=[Evidence(document=document, page=2, quote=value or "blank")],
    )


def _query(**changes: str) -> WorkspaceQuery:
    data = {
        "view": "firm",
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


def test_decision_buttons_open_the_matching_item() -> None:
    from caseboard.web.workspace.decisions import decision_actions

    urgent = [{"line": "Fifth request for right shoulder arthroscopy", "href": "/?document=a"}]
    critical = [{"glance": "Addresses disagree", "todo_href": "/?tab=todo&sel=1", "id": "1"}]
    actions = decision_actions(["Shoulder arthroscopy", "Addresses disagree"], urgent, critical)
    assert actions[0]["drawer"] is True
    assert actions[0]["href"] == "/?document=a"
    assert actions[1]["drawer"] is False
    assert actions[1]["href"].endswith("#todo-1")


def test_case_age_counts_whole_months() -> None:
    assert case_age("2023-04-23", date(2026, 10, 2)) == "3 yr 5 mo"
    assert case_age("2026-09-02", date(2026, 10, 2)) == "1 mo"
    assert case_age("", date(2026, 10, 2)) == ""


def test_file_sections_stay_in_page_order(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    store.put(DocType.source, "packet.pdf", SourceFile(filename="packet.pdf", page_count=11))
    store.put(DocType.segment, "other", Segment(id="other", source_file="packet.pdf", page_start=7, page_end=11, kind=SegmentKind.other))
    store.put(DocType.segment, "scene", Segment(id="scene", source_file="packet.pdf", page_start=3, page_end=6, kind=SegmentKind.incident_report))
    store.put(DocType.segment, "disc", Segment(id="disc", source_file="packet.pdf", page_start=1, page_end=2, kind=SegmentKind.discovery))
    chips = Workspace(store, _query(document="packet.pdf", page="1", drawer="1")).context()["viewer"]["chips"]
    assert [chip["label"] for chip in chips] == ["Discovery", "Incident Report", "Other"]
    assert [chip["active"] for chip in chips] == [True, False, False]


def test_named_stories_replace_generic_conflicts() -> None:
    facets = [
        _facet("addr-a", "patient.address", "7 Valley Drive, Nanuet, NY", "hipaa.pdf"),
        _facet("addr-b", "patient.address", "20510 Cypress Plaza Parkway, Cypress, Texas", "bop.pdf"),
        _facet("ssn", "patient.ssn", "123-84", "records.pdf"),
        _facet("knee", "injury.right_knee", "meniscus tear", "bop.pdf", kind=SegmentKind.clinical_note),
        _facet("knee-no", "injury.right_knee", "no recent traumatic injury", "katzman.pdf", kind=SegmentKind.expert_report),
        _facet("prior", "case.prior_index_number", "150940/2024", "complaint.pdf"),
        _facet("index", "case.index_number", "160000/2024", "complaint.pdf"),
        _facet("missing", "missing_document", "50-h transcript", "disc.pdf"),
    ]
    prior = facets[5]
    prior.evidence = [Evidence(document="complaint.pdf", page=2, quote="previously commenced under Index No. 150940/2024 CPLR 205")]
    findings = run_checks([], facets, [], [], [])
    by_code = {item.code: item for item in findings}
    assert "group_conflict" not in by_code
    assert "Nanuet" in by_code["critical_address"].message
    assert "123" not in by_code["critical_ssn"].message
    assert by_code["critical_defense"].message.startswith("Defense exam contradicts")
    assert "CPLR 205" in by_code["critical_index"].message
    assert "50-h transcript" in by_code["critical_missing"].message


def test_firm_home_leads_with_posture_and_hides_it_from_a_provider(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    store.put(DocType.facet, "name", _facet("name", "patient.name", "Justin W. Sapini", "complaint.pdf"))
    store.put(DocType.facet, "index", _facet("index", "case.index_number", "160000/2024", "complaint.pdf"))
    store.put(DocType.facet, "when", _facet("when", "accident.datetime", "2023-04-23", "complaint.pdf"))
    store.put(DocType.facet, "ssn", _facet("ssn", "patient.ssn", "123-84", "records.pdf"))
    store.put(
        DocType.timeline_event,
        "visit",
        TimelineEvent(
            id="visit",
            date="2023-04-24",
            label="Emergency visit",
            kind=EventKind.treatment,
            sensitivity=Sensitivity.provider_visible,
            sensitivity_reason="Treating clinical fact",
            origin="pdf",
            evidence=[Evidence(document="bills.pdf", page=1, quote="Arrival")],
        ),
    )
    ValidationRunner(store).run()
    firm = Workspace(store, _query()).context()
    assert firm["posture"] == ""
    assert firm["plate"][0]["v"] == "Justin W. Sapini"
    assert firm["plate"][1]["v"] == "160000/2024"
    store.put(
        DocType.summary,
        "case",
        CaseSummary(
            id="case",
            line="Surgery is waiting on a re-exam, and the papers still disagree on the address.",
            overview="A shoulder injury claim with an arthroscopy already performed.",
            actions=["Right shoulder arthroscopy"],
        ),
    )
    firm = Workspace(store, _query()).context()
    assert firm["posture"] == "Surgery is waiting on a re-exam, and the papers still disagree on the address."
    assert firm["status"]["summary"] == firm["posture"]
    assert firm["status"]["overview"].startswith("A shoulder injury")
    assert firm["status"]["actions"][0]["label"] == "Right shoulder arthroscopy"
    assert firm["status"]["cards"][0]["sub"] == "Since Apr 23, 2023"
    labels = [card["k"] for card in firm["status"]["cards"]]
    assert labels == ["Age of case", "Providers", "Critical", "PDFs"]
    assert firm["status"]["cards"][1]["v"] == "0"
    assert Workspace(store, _query(tab="todo")).context()["status"] is None
    ssn = next(item for item in firm["critical"] if item["code"] == "critical_ssn")
    assert "tab=todo" in ssn["todo_href"]
    assert f"sel={ssn['id']}" in ssn["todo_href"]
    assert firm["plate"][-1]["k"] == "Critical"
    assert firm["plate"][-1]["v"] == str(len(firm["critical"]))
    provider = Workspace(store, _query(view="provider")).context()
    assert provider["critical"] == []
    assert all("123" not in fact["value"] for fact in provider["records"]["facts"])


def test_extract_panel_lists_one_pdf(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    store.put(
        DocType.segment,
        "seg",
        Segment(
            id="seg",
            source_file="complaint.pdf",
            page_start=1,
            page_end=4,
            kind=SegmentKind.pleading,
            authored_by="Plaintiff",
        ),
    )
    store.put(DocType.facet, "index", _facet("index", "case.index_number", "160000/2024", "complaint.pdf"))
    detail = Workspace(store, _query(document="complaint.pdf", drawer="1", panel="extract")).context()["extract_detail"]
    assert detail["empty"] is False
    assert detail["segments"][0]["pages"] == "pp. 1–4"
    assert detail["facts"][0]["value"] == "160000/2024"
    assert "panel=extract" not in detail["facts"][0]["href"]
    hidden = Workspace(store, _query(view="provider", document="complaint.pdf", panel="extract")).context()["extract_detail"]
    assert hidden is None
