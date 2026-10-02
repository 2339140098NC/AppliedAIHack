"""Write Clio communications into the document store."""

import uuid

from caseboard.clio.client import ClioClient
from caseboard.domain.enums import CommSource, DocType, EventKind, Sensitivity
from caseboard.domain.models import Communication, Evidence, TimelineEvent
from caseboard.store.documents import DocumentStore

_TYPE_SOURCE = {
    "PhoneCommunication": CommSource.phone,
    "EmailCommunication": CommSource.email,
}


class ClioSync:
    def __init__(self, store: DocumentStore, client: ClioClient) -> None:
        self._store = store
        self._client = client

    def run(self, on_progress) -> int:
        on_progress("Reading Clio")
        matter_id, communications, notes, messages = self._client.sync_matter()
        self._store.delete_type(DocType.communication)
        self._store.delete_type(DocType.timeline_event, origin="clio")
        comm_rows = []
        event_rows = []
        for item in communications:
            source = _TYPE_SOURCE.get(item.get("type") or "", CommSource.email)
            record, event = _pair(
                matter_id=matter_id,
                clio_id=str(item.get("id")),
                source=source,
                subject=item.get("subject") or "",
                body=item.get("body") or "",
                occurred_on=item.get("received_at") or item.get("date"),
                kind=EventKind.call if source == CommSource.phone else EventKind.email,
            )
            comm_rows.append((record.id, record))
            event_rows.append((event.id, event))
        for item in notes:
            record, event = _pair(
                matter_id=matter_id,
                clio_id=str(item.get("id")),
                source=CommSource.note,
                subject=item.get("subject") or "",
                body=item.get("detail") or "",
                occurred_on=item.get("date"),
                kind=EventKind.note,
            )
            comm_rows.append((record.id, record))
            event_rows.append((event.id, event))
        for item in messages:
            record, event = _pair(
                matter_id=matter_id,
                clio_id=str(item.get("id")),
                source=CommSource.message,
                subject="",
                body=item.get("body") or "",
                occurred_on=item.get("created_at"),
                kind=EventKind.message,
            )
            comm_rows.append((record.id, record))
            event_rows.append((event.id, event))
        self._store.put_many(DocType.communication, comm_rows)
        self._store.put_many(DocType.timeline_event, event_rows)
        return len(comm_rows)


def _pair(
    *,
    matter_id: str,
    clio_id: str,
    source: CommSource,
    subject: str,
    body: str,
    occurred_on: str | None,
    kind: EventKind,
) -> tuple[Communication, TimelineEvent]:
    comm_id = str(uuid.uuid4())
    when = _date_only(occurred_on)
    label = subject.strip() or body.strip()[:80] or source.value
    communication = Communication(
        id=comm_id,
        clio_id=clio_id,
        source=source,
        subject=subject,
        body=body,
        occurred_on=when,
        sensitivity=Sensitivity.firm_only,
        matter_id=matter_id,
    )
    event = TimelineEvent(
        id=str(uuid.uuid4()),
        date=when,
        label=label,
        kind=kind,
        sensitivity=Sensitivity.firm_only,
        sensitivity_reason="Clio communication",
        evidence=[Evidence(document=f"clio:{clio_id}", page=1, quote=label[:240])],
        origin="clio",
    )
    return communication, event


def _date_only(value: str | None) -> str | None:
    if not value:
        return None
    return str(value)[:10]
