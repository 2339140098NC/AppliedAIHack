"""Load the store, run checks, and replace finding documents."""

from caseboard.domain.enums import DocType
from caseboard.domain.models import (
    Communication,
    ComparisonGroup,
    Facet,
    Segment,
    SourceFile,
    TimelineEvent,
)
from caseboard.store.documents import DocumentStore
from caseboard.validate.checks import run_checks


class ValidationRunner:
    def __init__(self, store: DocumentStore) -> None:
        self._store = store

    def run(self) -> int:
        sources = [SourceFile.model_validate(row) for row in self._store.list_type(DocType.source)]
        facets = [Facet.model_validate(row) for row in self._store.list_type(DocType.facet)]
        groups = [
            ComparisonGroup.model_validate(row) for row in self._store.list_type(DocType.group)
        ]
        events = [
            TimelineEvent.model_validate(row)
            for row in self._store.list_type(DocType.timeline_event)
        ]
        communications = [
            Communication.model_validate(row)
            for row in self._store.list_type(DocType.communication)
        ]
        segments = [Segment.model_validate(row) for row in self._store.list_type(DocType.segment)]
        findings = run_checks(sources, facets, groups, events, communications, segments)
        resolved = {
            row["code"]
            for row in self._store.list_type(DocType.validation)
            if row.get("resolved")
        }
        for item in findings:
            if item.code in resolved:
                item.resolved = True
        self._store.delete_type(DocType.validation)
        self._store.put_many(DocType.validation, [(item.id, item) for item in findings])
        return len(findings)
