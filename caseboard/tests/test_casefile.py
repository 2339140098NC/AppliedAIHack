"""The case tab keeps money, people, and disagreements scannable."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from caseboard.domain.enums import GroupStatus, SegmentKind, Sensitivity
from caseboard.domain.models import Charge, ComparisonGroup, Evidence, Facet, GroupEntry, Segment
from caseboard.extract.bills import BillLine, BillRead, charges_from
from caseboard.web.workspace.casefile import build_casefile
from caseboard.web.workspace.query import WorkspaceQuery


def _render(casefile: dict) -> str:
    root = Path(__file__).resolve().parents[1] / "caseboard" / "web" / "templates"
    env = Environment(loader=FileSystemLoader(root), autoescape=True)
    return env.get_template("partials/evidence.html").render(
        query=_query(),
        casefile=casefile,
        job={"running": False},
        gemini_ready=True,
        clio_connected=True,
    )


def _query() -> WorkspaceQuery:
    return WorkspaceQuery(
        view="firm",
        provider="montefiore",
        tab="evidence",
        document="",
        page=0,
        quote="",
        ev="",
        selected="",
        drawer="",
        panel="",
    )


def _facet(facet_id: str, key: str, value: str, document: str) -> Facet:
    return Facet(
        id=facet_id,
        facet_key=key,
        value=value,
        sensitivity=Sensitivity.firm_only,
        sensitivity_reason="test",
        segment_kind=SegmentKind.pleading,
        evidence=[Evidence(document=document, page=2, quote=value)],
    )


def test_provider_names_keep_the_comma_inside_the_name() -> None:
    listed = (
        "Advanced Rockland Chiropractic Offices, P.C. / Kevin M. Haggerty, D.C.; "
        "LHR - Rockland Diagnostic Imaging (New City, NY); P.C."
    )
    page = build_casefile(
        [_facet("hipaa", "hipaa.providers", listed, "hipaa.pdf")],
        [],
        [],
        [],
        _query(),
        lambda document, page: "",
    )
    names = [row["name"] for group in page["people"] for row in group["rows"]]
    assert names == [
        "Advanced Rockland Chiropractic Offices, P.C.",
        "Kevin M. Haggerty, D.C.",
        "LHR - Rockland Diagnostic Imaging (New City, NY)",
    ]


def test_summary_stays_one_sentence() -> None:
    from caseboard.glance.summary import clip_summary

    line = clip_summary(" ".join(["word"] * 40))
    assert len(line.split()) == 32
    assert line.endswith(".")


def test_bill_reading_keeps_a_stated_total_and_skips_a_blank_amount() -> None:
    rows = charges_from(
        "bill.pdf",
        BillRead(
            provider="SportsCare",
            lines=[
                BillLine(description="Total", amount="$1,200.00", page=3, quote="Total $1,200.00"),
                BillLine(description="Therapy", amount="none", page=1, quote="Therapy"),
            ],
        ),
    )
    assert len(rows) == 1
    assert rows[0].provider == "SportsCare"
    assert rows[0].amount == "$1,200.00"
    assert rows[0].document == "bill.pdf"
    assert rows[0].page == 3


def test_case_tab_shows_money_people_and_hides_identifier_conflicts() -> None:
    facets = [
        _facet("name", "patient.name", "Justin W. Sapini", "complaint.pdf"),
        _facet("addr-a", "patient.address", "7 Valley Drive", "hipaa.pdf"),
        _facet("addr-b", "patient.address", "20510 Cypress Plaza", "bop.pdf"),
        _facet("ssn-a", "patient.ssn", "123-84", "records.pdf"),
        _facet("ssn-b", "patient.ssn", "left blank", "hipaa.pdf"),
    ]
    groups = [
        ComparisonGroup(
            id="addr",
            facet_key="patient.address",
            status=GroupStatus.conflict,
            entries=[
                GroupEntry(facet_id="addr-a", value="7 Valley Drive", sensitivity=Sensitivity.firm_only, evidence=facets[1].evidence),
                GroupEntry(facet_id="addr-b", value="20510 Cypress Plaza", sensitivity=Sensitivity.firm_only, evidence=facets[2].evidence),
            ],
        ),
        ComparisonGroup(
            id="ssn",
            facet_key="patient.ssn",
            status=GroupStatus.conflict,
            entries=[
                GroupEntry(facet_id="ssn-a", value="123-84", sensitivity=Sensitivity.firm_only, evidence=facets[3].evidence),
                GroupEntry(facet_id="ssn-b", value="left blank", sensitivity=Sensitivity.firm_only, evidence=facets[4].evidence),
            ],
        ),
    ]
    segments = [
        Segment(id="bill", source_file="montefiore.pdf", page_start=1, page_end=1, kind=SegmentKind.bill, facility="Montefiore Nyack"),
        Segment(id="exam", source_file="katzman.pdf", page_start=1, page_end=2, kind=SegmentKind.expert_report, authored_by="Katzman"),
    ]
    charges = [
        Charge(id="a", provider="Montefiore Nyack", description="Total", amount="$400.00", document="montefiore.pdf", page=1, quote="Total $400"),
        Charge(id="b", provider="Montefiore Nyack", description="Balance", amount="$900", document="other.pdf", page=1, quote="Balance $900"),
    ]
    page = build_casefile(facets, groups, segments, charges, _query(), lambda document, page: f"{document} p.{page}")
    bill = page["expenses"][0]
    assert bill["conflict"] is True
    assert bill["headline"] == ""
    assert {line["amount"] for line in bill["lines"]} == {"$400.00", "$900"}
    client = page["people"][0]
    assert client["role"] == "Client"
    assert client["rows"][0]["mark"] == "Address disagrees"
    roles = {group["role"] for group in page["people"]}
    assert "Provider" in roles
    assert "Expert" in roles
    titles = [item["title"] for item in page["disagreements"]]
    assert "Patient address" in titles
    html = _render(page)
    assert "Patient address" in html
    assert "Two totals" in html
    assert "Address disagrees" in html
    assert all(not title.lower().startswith("treatment") for title in titles)
    assert all("123" not in row["value"] for item in page["disagreements"] for row in item["sides"])
