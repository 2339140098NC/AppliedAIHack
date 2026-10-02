"""How a Clio record is labeled on the timeline and in the drawer."""

from caseboard.domain.enums import CommSource
from caseboard.domain.models import Communication


def comm_meta(record: Communication) -> list[dict[str, str]]:
    """From, to, author, and the other party. Empty names are left off."""
    rows: list[tuple[str, str]] = []
    if record.source == CommSource.email:
        rows.append(("From", record.sender))
        if record.recipients:
            rows.append(("To", ", ".join(record.recipients)))
    elif record.source == CommSource.phone:
        rows.append(("Logged by", record.author))
        rows.append(("With", record.sender))
    elif record.source == CommSource.note:
        rows.append(("Author", record.author))
        rows.append(("Contact", record.sender))
    elif record.source == CommSource.message:
        rows.append(("From", record.sender or record.author))
    return [{"label": label, "value": value} for label, value in rows if value.strip()]


def comm_sub(record: Communication) -> str:
    """The line under a timeline subject: who, then the clock."""
    if record.source == CommSource.email and record.sender:
        who = f"From {record.sender}"
    elif record.source == CommSource.phone and record.author:
        who = f"Logged by {record.author}"
    elif record.source == CommSource.note and record.author:
        who = f"By {record.author}"
    elif record.sender:
        who = record.sender
    else:
        who = ""
    return " · ".join(part for part in (who, record.occurred_time) if part)
