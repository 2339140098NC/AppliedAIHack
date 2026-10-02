"""The individual case stories behind the home screen."""

from caseboard.domain.enums import SegmentKind, Severity
from caseboard.domain.models import Evidence, Facet, Finding, Segment, TimelineEvent
from caseboard.extract.assemble import status_for
from caseboard.extract.compare import calendar_day, compare_value, drop_combined_locations, is_denial
from caseboard.validate.emit import cites, emit, finding, tokens_for, unique_facets, values_for

_CLINICAL = {
    SegmentKind.clinical_note,
    SegmentKind.imaging_report,
    SegmentKind.operative_report,
    SegmentKind.bill,
}


def addresses(facets: list[Facet]) -> Finding | None:
    distinct = values_for(facets, "patient.address")
    if len(distinct) < 2:
        return None
    title = "Three different addresses for the client" if len(distinct) >= 3 else "Addresses for the client disagree"
    return finding("critical_address", Severity.conflict, title, "; ".join(distinct) + ".", facets)


def location(facets: list[Facet]) -> Finding | None:
    kept = {compare_value("accident.location", value) for value in drop_combined_locations([facet.value for facet in facets])}
    kept.discard("")
    if len(kept) < 2:
        return None
    shown = [facet for facet in facets if compare_value("accident.location", facet.value) in kept]
    return finding("critical_location", Severity.conflict, "Accident location doesn't match", "; ".join(values_for(shown, "accident.location")) + ".", shown)


def scene(by_key: dict[str, list[Facet]], events: list[TimelineEvent]) -> Finding | None:
    stated = [facet for facet in by_key.get("accident.injury_at_scene", []) if facet.value and is_denial(facet.value)]
    if not stated:
        return None
    accident = ""
    for facet in by_key.get("accident.datetime", []):
        accident = calendar_day(facet.value) or accident
    later = [
        event
        for event in events
        if event.origin == "pdf"
        and event.date
        and event.kind.value in {"treatment", "imaging", "surgery"}
        and (not accident or (calendar_day(event.date) or "") > accident)
    ]
    if not later:
        return None
    return finding("critical_scene", Severity.conflict, "Incident report says no injury", "The client was treated after the scene report.", stated + later)


def defense(by_key: dict[str, list[Facet]]) -> Finding | None:
    cited: list[Facet] = []
    parts: list[str] = []
    for key, facets in by_key.items():
        if not key.startswith("injury."):
            continue
        denials = [facet for facet in facets if facet.value and is_denial(facet.value)]
        affirms = [facet for facet in facets if facet.value and not is_denial(facet.value)]
        if denials and affirms:
            cited.extend(denials + affirms)
            parts.append(key.split(".", 1)[1].replace("_", " "))
    conclusions = [facet for facet in by_key.get("expert.conclusion", []) if facet.value and is_denial(facet.value)]
    injuries = [
        facet
        for key, facets in by_key.items()
        if key.startswith("injury.")
        for facet in facets
        if facet.value and not is_denial(facet.value)
    ]
    if conclusions and injuries:
        cited.extend(conclusions + injuries)
    if not cited:
        return None
    detail = "Disagreement on " + ", ".join(parts) + "." if parts else "A defense opinion denies an injury the treating records state."
    return finding("critical_defense", Severity.conflict, "Defense exam contradicts the treating injuries", detail, unique_facets(cited))


def index_numbers(by_key: dict[str, list[Facet]]) -> Finding | None:
    current = by_key.get("case.index_number", [])
    prior = by_key.get("case.prior_index_number", [])
    current_tokens = tokens_for(current, "case.index_number")
    prior_tokens = tokens_for(prior, "case.prior_index_number")
    if not current_tokens or not prior_tokens or current_tokens == prior_tokens:
        return None
    detail = "Current " + ", ".join(values_for(current, "case.index_number")) + ". Earlier " + ", ".join(values_for(prior, "case.prior_index_number")) + "."
    blob = " ".join((facet.value or "") + " " + " ".join(cite.quote for cite in facet.evidence) for facet in current + prior)
    if "205" in blob:
        detail += " The earlier case was renewed under CPLR 205."
    return finding("critical_index", Severity.conflict, "Two index numbers", detail, current + prior)


def report_dates(facets: list[Facet]) -> Finding | None:
    if len(tokens_for(facets, "expert.report_date")) < 2:
        return None
    blob = " ".join(facet.authored_by + " " + " ".join(cite.document for cite in facet.evidence) for facet in facets).lower()
    title = "Katzman report carries two dates" if "katzman" in blob else "The expert report carries two dates"
    return finding("critical_report_dates", Severity.conflict, title, "; ".join(values_for(facets, "expert.report_date")) + ".", facets)


def nofault(facets: list[Facet]) -> Finding | None:
    if not facets or status_for([facet.value for facet in facets], key="benefits.nofault").value != "incomplete":
        return None
    return finding("critical_nofault", Severity.incomplete, "No-fault claim number is blank", "The carrier is named and the number is missing.", facets)


def ssn(facets: list[Facet]) -> Finding | None:
    hits = [facet for facet in facets if "ssn" in facet.facet_key.lower() and any(ch.isdigit() for ch in (facet.value or ""))]
    if not hits:
        return None
    return finding("critical_ssn", Severity.sensitive, "Partial Social Security number is visible", "Covered digits stay covered. The page still shows characters beside the redaction.", hits)


def draft(facets: list[Facet], segments: list[Segment]) -> Finding | None:
    hits = [facet for facet in facets if facet.facet_key == "draft.complaint"]
    by_file: dict[str, set[SegmentKind]] = {}
    for segment in segments:
        by_file.setdefault(segment.source_file, set()).add(segment.kind)
    mixed = [name for name, kinds in by_file.items() if SegmentKind.pleading in kinds and kinds & _CLINICAL]
    if not hits and not mixed:
        return None
    evidence = cites(hits) + [Evidence(document=name, page=1, quote="") for name in mixed]
    return emit("critical_draft", Severity.sensitive, "Split the medical bundle before sharing", "A draft pleading is inside a medical file.", [facet.id for facet in hits], evidence)


def chest(facets: list[Facet], events: list[TimelineEvent]) -> Finding | None:
    hits: list[Facet | TimelineEvent] = []
    for facet in facets:
        if _chest_text(f"{facet.facet_key} {facet.value or ''} " + " ".join(cite.quote for cite in facet.evidence)):
            hits.append(facet)
    for event in events:
        blob = f"{event.label} {event.date or ''} " + " ".join(cite.quote for cite in event.evidence)
        if _chest_text(blob):
            hits.append(event)
    if not hits:
        return None
    return finding("critical_chest", Severity.sensitive, "Defense review used a 2018 chest x-ray", "That date is outside the authorization window.", hits)


def imagers(by_key: dict[str, list[Facet]]) -> Finding | None:
    listed = [facet for facet in by_key.get("hipaa.providers", []) if facet.value]
    named = [facet for facet in by_key.get("injury.imaging_provider", []) if facet.value]
    if not listed or not named:
        return None
    haystack = " ".join(_norm(facet.value or "") for facet in listed)
    missing = [facet for facet in named if _norm(facet.value or "") not in haystack]
    if not missing:
        return None
    return finding("critical_imagers", Severity.sensitive, "Imagers are missing from the HIPAA provider list", ", ".join(facet.value or "" for facet in missing) + ".", listed + missing)


def missing_documents(facets: list[Facet]) -> Finding | None:
    named = [facet for facet in facets if facet.value and facet.value.strip()]
    if not named:
        return None
    names: list[str] = []
    for facet in named:
        if facet.value and facet.value.strip() not in names:
            names.append(facet.value.strip())
    return finding("critical_missing", Severity.incomplete, "Documents mentioned but not in the file", ", ".join(names) + ".", named)


def _chest_text(value: str) -> bool:
    text = value.lower()
    return "chest" in text and "2018" in text


def _norm(value: str) -> str:
    return " ".join(value.lower().split())
