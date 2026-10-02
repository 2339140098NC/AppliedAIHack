"""Validations run against stored JSON without calling Gemini or Clio."""

from pathlib import Path

from caseboard.domain.enums import (
    CommSource,
    DocType,
    EventKind,
    SegmentKind,
    Sensitivity,
    Severity,
)
from caseboard.domain.models import Communication, Evidence, Facet, TimelineEvent
from caseboard.extract.assemble import build_groups, status_for
from caseboard.extract.sensitivity import facet_sensitivity
from caseboard.store.documents import DocumentStore
from caseboard.validate.runner import ValidationRunner


def test_sensitive_keys_stay_with_the_firm() -> None:
    sensitivity, _reason = facet_sensitivity(SegmentKind.clinical_note, "benefits.medicaid")
    assert sensitivity == Sensitivity.firm_only
    sensitivity, _reason = facet_sensitivity(SegmentKind.pleading, "patient.name")
    assert sensitivity == Sensitivity.firm_only
    sensitivity, _reason = facet_sensitivity(SegmentKind.clinical_note, "injury.right_knee")
    assert sensitivity == Sensitivity.provider_visible


def test_groups_mark_conflict_and_incomplete() -> None:
    assert status_for(["Cedar Street", "I-95 Exit 16"]) == status_for(["Cedar Street", "I-95 Exit 16"])
    from caseboard.domain.enums import GroupStatus

    assert status_for(["Cedar Street", "I-95 Exit 16"]) == GroupStatus.conflict
    assert status_for(["12/21/1995", None]) == GroupStatus.incomplete
    assert status_for(["Nyack", "nyack"]) == GroupStatus.consistent


def test_runner_writes_findings(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    visible_legal = Facet(
        id="facet-legal",
        facet_key="patient.name",
        value="Justin Sapini",
        redacted=False,
        sensitivity=Sensitivity.provider_visible,
        sensitivity_reason="bad label",
        authored_by="complaint",
        segment_kind=SegmentKind.pleading,
        evidence=[Evidence(document="complaint.pdf", page=2, quote="Justin Sapini")],
    )
    secret = Facet(
        id="facet-ssn",
        facet_key="patient.ssn",
        value="123456789",
        redacted=False,
        sensitivity=Sensitivity.firm_only,
        sensitivity_reason="Sensitive fact key",
        authored_by="form",
        segment_kind=SegmentKind.hipaa_authorization,
        evidence=[Evidence(document="records.pdf", page=241, quote="123-84")],
    )
    knee_a = Facet(
        id="knee-a",
        facet_key="injury.right_knee",
        value="meniscus tear",
        sensitivity=Sensitivity.provider_visible,
        sensitivity_reason="Treating clinical fact",
        segment_kind=SegmentKind.clinical_note,
        evidence=[Evidence(document="bop.pdf", page=6, quote="meniscus")],
    )
    knee_b = Facet(
        id="knee-b",
        facet_key="injury.right_knee",
        value="no recent traumatic injury",
        sensitivity=Sensitivity.firm_only,
        sensitivity_reason="Legal, defense, or identity source",
        authored_by="Katzman",
        segment_kind=SegmentKind.expert_report,
        evidence=[Evidence(document="katzman.pdf", page=3, quote="no recent")],
    )
    store.put(DocType.facet, visible_legal.id, visible_legal)
    store.put(DocType.facet, secret.id, secret)
    store.put(DocType.facet, knee_a.id, knee_a)
    store.put(DocType.facet, knee_b.id, knee_b)
    for group in build_groups(
        [visible_legal, secret, knee_a, knee_b]
    ):
        store.put(DocType.group, group.id, group)
    store.put(
        DocType.communication,
        "comm-1",
        Communication(
            id="comm-1",
            clio_id="99",
            source=CommSource.phone,
            body="settlement talk",
            sensitivity=Sensitivity.provider_visible,
            matter_id="1",
        ),
    )
    store.put(
        DocType.timeline_event,
        "event-1",
        TimelineEvent(
            id="event-1",
            date=None,
            label="Collision",
            kind=EventKind.accident,
            sensitivity=Sensitivity.provider_visible,
            sensitivity_reason="Clinical or accident event",
            origin="pdf",
            evidence=[Evidence(document="complaint.pdf", page=2, quote="April 23")],
        ),
    )
    count = ValidationRunner(store).run()
    findings = store.list_type(DocType.validation)
    codes = {row["code"] for row in findings}
    assert count == len(findings)
    assert "clinical_label_on_legal_source" in codes
    assert "redaction_ignored" in codes
    assert "group_conflict" in codes
    assert "clio_not_firm_only" in codes
    assert "timeline_missing_date" in codes
    assert any(row["severity"] == Severity.sensitive.value for row in findings)
