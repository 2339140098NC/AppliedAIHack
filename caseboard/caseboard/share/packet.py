"""Include, hold back, and send the records on a provider preview."""

from datetime import datetime, timezone

from caseboard.domain.enums import DocType
from caseboard.domain.models import ProviderShare
from caseboard.store.documents import DocumentStore
from caseboard.store.upstash import UpstashDocumentStore

Store = DocumentStore | UpstashDocumentStore


def load_share(store: Store, provider: str) -> ProviderShare:
    """The saved packet for this provider, or an empty one that includes everything."""
    for row in store.list_type(DocType.share):
        packet = ProviderShare.model_validate(row)
        if packet.provider == provider:
            return packet
    return ProviderShare(id=provider, provider=provider)


def toggle_item(store: Store, provider: str, record_id: str) -> ProviderShare:
    """Hold a record back, or include it again."""
    packet = load_share(store, provider)
    excluded = list(packet.excluded)
    if record_id in excluded:
        excluded.remove(record_id)
    else:
        excluded.append(record_id)
    packet.excluded = excluded
    store.put(DocType.share, packet.id, packet)
    return packet


def send_packet(store: Store, provider: str, eligible: list[str]) -> ProviderShare:
    """Record the included records as sent. Held-back ids stay off the packet."""
    packet = load_share(store, provider)
    held = set(packet.excluded)
    packet.sent_ids = [item for item in eligible if item not in held]
    packet.sent_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    store.put(DocType.share, packet.id, packet)
    return packet


def share_status(packet: ProviderShare, eligible: list[str]) -> dict:
    """Counts for the preview bar."""
    held = {item for item in packet.excluded if item in eligible}
    included = len(eligible) - len(held)
    included_ids = {item for item in eligible if item not in held}
    return {
        "included": included,
        "held": len(held),
        "held_ids": [item for item in packet.excluded if item in held],
        "sent": bool(packet.sent_at),
        "sent_label": _sent_label(packet.sent_at),
        "changed": bool(packet.sent_at) and set(packet.sent_ids) != included_ids,
    }


def _sent_label(value: str) -> str:
    if len(value) < 16:
        return ""
    hour = int(value[11:13])
    minute = value[14:16]
    suffix = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    month, day = value[5:7], str(int(value[8:10]))
    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{names[int(month) - 1]} {day}, {value[:4]}, {hour12}:{minute} {suffix}"
