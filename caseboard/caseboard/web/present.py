"""Shape store rows for the three dashboard panels."""

from caseboard.domain.enums import Audience, DocType, Sensitivity
from caseboard.domain.models import ComparisonGroup, Finding, TimelineEvent
from caseboard.extract.assemble import status_for
from caseboard.store.documents import DocumentStore


def timeline_rows(store: DocumentStore, audience: Audience) -> list[dict]:
    events = [TimelineEvent.model_validate(row) for row in store.list_type(DocType.timeline_event)]
    visible = [event for event in events if _allowed(event.sensitivity, audience)]
    visible.sort(key=lambda event: (event.date or "9999-99-99", event.time or "", event.label))
    return [event.model_dump(mode="json") for event in visible]


def group_rows(store: DocumentStore, audience: Audience) -> list[dict]:
    rows = []
    for raw in store.list_type(DocType.group):
        group = ComparisonGroup.model_validate(raw)
        entries = [
            entry
            for entry in group.entries
            if _allowed(entry.sensitivity, audience)
        ]
        if not entries:
            continue
        status = status_for([entry.value for entry in entries])
        payload = group.model_dump(mode="json")
        payload["status"] = status.value
        payload["entries"] = [entry.model_dump(mode="json") for entry in entries]
        rows.append(payload)
    return rows


def finding_rows(store: DocumentStore) -> list[dict]:
    findings = [Finding.model_validate(row) for row in store.list_type(DocType.validation)]
    findings.sort(key=lambda item: (item.severity.value, item.message))
    return [item.model_dump(mode="json") for item in findings]


def _allowed(sensitivity: Sensitivity, audience: Audience) -> bool:
    if audience == Audience.firm:
        return True
    return sensitivity == Sensitivity.provider_visible
