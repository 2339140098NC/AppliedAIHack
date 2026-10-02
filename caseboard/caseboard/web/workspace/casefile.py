"""The case tab: money, people, and only the facts that disagree."""

import re
from collections import defaultdict

from caseboard.domain.enums import GroupStatus, SegmentKind
from caseboard.domain.models import Charge, ComparisonGroup, Facet, Segment
from caseboard.extract.compare import compare_value
from caseboard.web.workspace.query import WorkspaceQuery

_CLINICAL = {
    SegmentKind.clinical_note,
    SegmentKind.imaging_report,
    SegmentKind.operative_report,
    SegmentKind.bill,
}
_HIDDEN = ("ssn", "license", "policy", "medicaid", "nofault", "employee")
_ROLE_ORDER = ("Client", "Expert", "Provider", "Imaging", "On the HIPAA form")


def build_casefile(
    facets: list[Facet],
    groups: list[ComparisonGroup],
    segments: list[Segment],
    charges: list[Charge],
    query: WorkspaceQuery,
    source_label,
) -> dict:
    """Sections a lawyer can scan. Identifier values stay off this page."""
    return {
        "expenses": _expenses(charges, query, source_label),
        "people": _people(facets, groups, segments, query),
        "disagreements": _disagreements(groups, query, source_label),
    }


def _expenses(charges: list[Charge], query: WorkspaceQuery, source_label) -> list[dict]:
    buckets: dict[str, list[Charge]] = defaultdict(list)
    for charge in charges:
        buckets[_key(charge.provider or "Unnamed biller")].append(charge)
    cards = []
    for rows in buckets.values():
        name = max((row.provider for row in rows), key=len)
        totals = [row for row in rows if _is_total(row.description)]
        amounts = {_money(row.amount) for row in totals}
        amounts.discard("")
        conflict = len(amounts) > 1
        headline = totals[0].amount if len(amounts) == 1 else ""
        shown = totals if conflict else [row for row in rows if row not in totals][:8]
        cards.append({
            "provider": name,
            "conflict": conflict,
            "headline": headline,
            "lines": [_line(row, query, source_label) for row in shown],
        })
    cards.sort(key=lambda card: card["provider"].lower())
    return cards


def _people(
    facets: list[Facet],
    groups: list[ComparisonGroup],
    segments: list[Segment],
    query: WorkspaceQuery,
) -> list[dict]:
    rows: list[dict] = []
    rows.extend(_client(facets, groups))
    rows.extend(_from_segments(segments))
    rows.extend(_named(facets, "injury.imaging_provider", "Imaging"))
    rows.extend(_named(facets, "hipaa.providers", "On the HIPAA form"))
    merged = _merge_people(rows)
    by_role: dict[str, list[dict]] = defaultdict(list)
    for person in merged:
        by_role[person["role"]].append(person)
    sections = []
    for role in _ROLE_ORDER:
        people = by_role.get(role)
        if not people:
            continue
        people.sort(key=lambda item: item["name"].lower())
        for person in people:
            person["href"] = _href(query, person.get("document", ""), person.get("page", 1))
        sections.append({"role": role, "rows": people})
    return sections


def _disagreements(groups: list[ComparisonGroup], query: WorkspaceQuery, source_label) -> list[dict]:
    cards = []
    for group in groups:
        if group.status != GroupStatus.conflict or _skip_disagreement(group.facet_key):
            continue
        seen: dict[str, dict] = {}
        for entry in group.entries:
            mark = compare_value(group.facet_key, entry.value or "")
            if mark in seen:
                continue
            cite = entry.evidence[0] if entry.evidence else None
            document = cite.document if cite else ""
            page = cite.page if cite else 1
            seen[mark] = {
                "value": (entry.value or "").strip() or "Left blank",
                "source": source_label(document, page) if document else "",
                "href": _href(query, document, page, cite.quote if cite else ""),
            }
        values = list(seen.values())
        if len(values) < 2:
            continue
        cards.append({"title": _title(group.facet_key), "values": values})
    cards.sort(key=lambda card: card["title"].lower())
    return cards


def _client(facets: list[Facet], groups: list[ComparisonGroup]) -> list[dict]:
    names = _values(facets, "patient.name")
    if not names:
        return []
    marks = []
    if len({_key(name) for name in names}) > 1:
        marks.append("Name disagrees")
    if any(group.facet_key == "patient.address" and group.status == GroupStatus.conflict for group in groups):
        marks.append("Address disagrees")
    cite = _first_cite(facets, "patient.name")
    return [{
        "name": names[0],
        "role": "Client",
        "meta": "",
        "mark": " · ".join(marks),
        "document": cite[0],
        "page": cite[1],
    }]


def _from_segments(segments: list[Segment]) -> list[dict]:
    facilities: dict[str, dict] = {}
    authors: dict[str, dict] = {}
    for segment in segments:
        facility = segment.facility.strip()
        author = segment.authored_by.strip()
        if segment.kind == SegmentKind.expert_report:
            name = author or facility
            if name:
                _touch(authors, name, "Expert", segment)
            continue
        if facility and segment.kind in _CLINICAL:
            _touch(facilities, facility, "Provider", segment)
    return list(facilities.values()) + list(authors.values())


def _named(facets: list[Facet], key: str, role: str) -> list[dict]:
    rows = []
    for facet in facets:
        if facet.facet_key != key:
            continue
        cite = facet.evidence[0] if facet.evidence else None
        for name in _split(facet.value or ""):
            rows.append({
                "name": name,
                "role": role,
                "meta": "",
                "mark": "",
                "document": cite.document if cite else "",
                "page": cite.page if cite else 1,
                "files": {cite.document} if cite and cite.document else set(),
            })
    return rows


def _merge_people(rows: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for row in rows:
        slot = merged.setdefault(_key(row["name"]), {
            "name": row["name"],
            "roles": [],
            "files": set(),
            "mark": "",
            "document": "",
            "page": 1,
        })
        if row["role"] not in slot["roles"]:
            slot["roles"].append(row["role"])
        slot["files"].update(row.get("files") or set())
        if row.get("mark"):
            slot["mark"] = row["mark"]
        if row.get("document") and not slot["document"]:
            slot["document"] = row["document"]
            slot["page"] = row.get("page") or 1
        if len(row["name"]) > len(slot["name"]):
            slot["name"] = row["name"]
    people = []
    for slot in merged.values():
        count = len(slot["files"])
        meta = f"{count} record{'s' if count != 1 else ''}" if count else ""
        people.append({
            "name": slot["name"],
            "role": _primary_role(slot["roles"]),
            "meta": meta,
            "mark": slot["mark"],
            "document": slot["document"],
            "page": slot["page"],
        })
    return people


def _touch(bucket: dict[str, dict], name: str, role: str, segment: Segment) -> None:
    slot = bucket.setdefault(_key(name), {
        "name": name,
        "role": role,
        "meta": "",
        "mark": "",
        "document": segment.source_file,
        "page": segment.page_start,
        "files": set(),
    })
    if segment.source_file:
        slot["files"].add(segment.source_file)
    if len(name) > len(slot["name"]):
        slot["name"] = name


def _line(charge: Charge, query: WorkspaceQuery, source_label) -> dict:
    when = charge.service_date
    label = charge.description
    if when:
        label = f"{label} · {when}"
    return {
        "label": label,
        "amount": charge.amount,
        "source": source_label(charge.document, charge.page),
        "href": _href(query, charge.document, charge.page, charge.quote),
    }


def _values(facets: list[Facet], key: str) -> list[str]:
    found = []
    for facet in facets:
        value = (facet.value or "").strip()
        if facet.facet_key == key and value and value not in found:
            found.append(value)
    return found


def _first_cite(facets: list[Facet], key: str) -> tuple[str, int]:
    for facet in facets:
        if facet.facet_key == key and facet.evidence:
            cite = facet.evidence[0]
            return cite.document, cite.page
    return "", 1


def _split(value: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[;,]", value) if part.strip()]
    if len(parts) > 1 and all(3 <= len(part) <= 60 for part in parts):
        return parts[:12]
    text = " ".join(value.split())
    return [text[:80]] if text else []


def _primary_role(roles: list[str]) -> str:
    for role in _ROLE_ORDER:
        if role in roles:
            return role
    return roles[0]


def _href(query: WorkspaceQuery, document: str, page: int, quote: str = "") -> str:
    if not document:
        return ""
    return query.url(document=document, page=page, quote=quote, sel="", tab="evidence")


def _skip_disagreement(key: str) -> bool:
    """Identifiers stay off this page. Different procedures are not a contradiction."""
    if key.startswith("treatment.") or key == "missing_document":
        return True
    return _hidden(key)


def _hidden(key: str) -> bool:
    text = key.lower().replace("_", "").replace("-", "")
    return any(bit in text for bit in _HIDDEN)


def _is_total(description: str) -> bool:
    text = description.lower()
    return any(bit in text for bit in ("total", "balance", "amount due"))


def _money(amount: str) -> str:
    digits = re.sub(r"[^0-9.]", "", amount)
    if not digits:
        return ""
    try:
        return f"{float(digits):.2f}"
    except ValueError:
        return digits


def _key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _title(key: str) -> str:
    text = key.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:] if text else "Fact"
