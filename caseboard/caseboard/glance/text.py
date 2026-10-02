"""The text a lawyer's glance is read from."""

import hashlib

from caseboard.domain.models import Communication, TimelineEvent

CATEGORIES = (
    "Accident",
    "Treatment",
    "Imaging",
    "Surgery",
    "Bill",
    "Pleading",
    "Discovery",
    "Expert",
    "Insurance",
    "Client",
    "Court",
)


def glance_key(event: TimelineEvent) -> str:
    """A key that survives a resync. Clio ids are stable. PDF rows are content."""
    evidence = event.evidence[0] if event.evidence else None
    document = evidence.document if evidence else ""
    if document.startswith("clio:"):
        return document
    page = evidence.page if evidence else 0
    raw = f"{event.date or ''}|{event.label}|{document}|{page}"
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"pdf:{digest}"


def glance_text(event: TimelineEvent, comm: Communication | None) -> str:
    """Extracted quote for a PDF, or the message plus who sent it."""
    evidence = event.evidence[0] if event.evidence else None
    quote = (evidence.quote if evidence else "")[:240]
    if comm is None:
        return " ".join(part for part in (event.label, quote) if part)[:500]
    people = [comm.sender or comm.author, *comm.recipients[:2]]
    who = ", ".join(name for name in people if name)
    body = comm.body.replace("\n", " ")[:360]
    return " ".join(part for part in (comm.subject, body, who) if part)[:500]
