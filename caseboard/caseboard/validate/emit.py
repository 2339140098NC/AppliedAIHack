"""Build one finding from facets without repeating citation plumbing."""

import uuid

from caseboard.domain.enums import Severity
from caseboard.domain.models import Evidence, Facet, Finding
from caseboard.extract.assemble import status_for
from caseboard.extract.compare import compare_value


def finding(code: str, severity: Severity, title: str, detail: str, records: list) -> Finding:
    """A finding whose message is a title, then one sentence of detail."""
    return emit(
        code,
        severity,
        title,
        detail,
        [record.id for record in records],
        cites(records),
    )


def emit(
    code: str,
    severity: Severity,
    title: str,
    detail: str,
    record_ids: list[str],
    evidence: list[Evidence],
) -> Finding:
    return Finding(
        id=str(uuid.uuid4()),
        code=code,
        severity=severity,
        message=f"{title}. {detail}",
        record_ids=record_ids,
        evidence=evidence,
    )


def cites(records: list) -> list[Evidence]:
    seen: set[tuple[str, int, str]] = set()
    found: list[Evidence] = []
    for record in records:
        for cite in getattr(record, "evidence", []):
            mark = (cite.document, cite.page, cite.quote)
            if not cite.document or mark in seen:
                continue
            seen.add(mark)
            found.append(cite)
    return found


def values_for(facets: list[Facet], key: str) -> list[str]:
    rows: list[str] = []
    for token in tokens_for(facets, key):
        choices = [
            facet.value.strip()
            for facet in facets
            if facet.value and compare_value(key, facet.value) == token
        ]
        if choices:
            rows.append(max(choices, key=len))
    return rows


def tokens_for(facets: list[Facet], key: str) -> list[str]:
    seen: list[str] = []
    for facet in facets:
        token = compare_value(key, facet.value)
        if token and token not in seen:
            seen.append(token)
    return seen


def unique_facets(facets: list[Facet]) -> list[Facet]:
    seen: set[str] = set()
    rows = []
    for facet in facets:
        if facet.id in seen:
            continue
        seen.add(facet.id)
        rows.append(facet)
    return rows


def when_incomplete(code: str, title: str, detail: str, facets: list[Facet], key: str) -> Finding | None:
    if not facets or status_for([facet.value for facet in facets], key=key).value != "incomplete":
        return None
    return finding(code, Severity.incomplete, title, detail, facets)


def when_distinct(
    code: str,
    severity: Severity,
    title: str,
    detail: str,
    facets: list[Facet],
    key: str,
) -> Finding | None:
    if len(tokens_for(facets, key)) < 2:
        return None
    return finding(code, severity, title, detail, facets)


def when_present(code: str, severity: Severity, title: str, detail: str, facets: list[Facet]) -> Finding | None:
    hits = [facet for facet in facets if facet.value and facet.value.strip()]
    if not hits:
        return None
    return finding(code, severity, title, detail, hits)
