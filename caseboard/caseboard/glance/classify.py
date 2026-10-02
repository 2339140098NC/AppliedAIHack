"""Ask Gemini for a one-line lawyer's reading of each timeline item."""

import json

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from caseboard.domain.enums import DocType
from caseboard.domain.models import Communication, ItemGlance, TimelineEvent
from caseboard.errors import CaseboardError
from caseboard.glance.text import CATEGORIES, glance_key, glance_text
from caseboard.store.documents import DocumentStore
from caseboard.store.upstash import UpstashDocumentStore

Store = DocumentStore | UpstashDocumentStore
_BATCH = 40

_PROMPT = """
You are reading a New York personal-injury file for the lawyer on the case.
For each item, return:
- category: exactly one of """ + ", ".join(CATEGORIES) + """
- line: at most 12 words a lawyer can scan. Name the fact, not the document type. Do not repeat the date.
- urgent: true only when the lawyer should act, a benefit is exhausted, a court or surgery date is being set, a demand is unanswered, or a fact changes the claim. A routine visit, note, or status email is false.
Use the given id unchanged. Do not invent facts that are not in the text.
""".strip()


class _Item(BaseModel):
    id: str
    category: str
    line: str
    urgent: bool = False


class _Batch(BaseModel):
    items: list[_Item] = Field(default_factory=list)


def classify_timeline(store: Store, api_key: str, model: str, on_progress) -> int:
    """Replace stored glances from the text already on the timeline."""
    if not api_key.strip():
        raise CaseboardError("GEMINI_API_KEY is not set")
    events = [TimelineEvent.model_validate(row) for row in store.list_type(DocType.timeline_event)]
    comms = {
        item.clio_id: item
        for item in (Communication.model_validate(row) for row in store.list_type(DocType.communication))
    }
    packets = [_packet(event, comms) for event in events]
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=120_000))
    rows: list[tuple[str, ItemGlance]] = []
    for start in range(0, len(packets), _BATCH):
        chunk = packets[start : start + _BATCH]
        on_progress(f"Reading {start + 1}–{start + len(chunk)} of {len(packets)}")
        rows.extend(_read(client, model, chunk))
    store.delete_type(DocType.glance)
    store.put_many(DocType.glance, rows)
    return len(rows)


def _packet(event: TimelineEvent, comms: dict[str, Communication]) -> dict:
    evidence = event.evidence[0] if event.evidence else None
    document = evidence.document if evidence else ""
    comm = comms.get(document.removeprefix("clio:")) if document.startswith("clio:") else None
    return {"id": glance_key(event), "kind": event.kind.value, "text": glance_text(event, comm)}


def _read(client: genai.Client, model: str, chunk: list[dict]) -> list[tuple[str, ItemGlance]]:
    response = client.models.generate_content(
        model=model,
        contents=[_PROMPT, json.dumps(chunk)],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=_Batch.model_json_schema(),
            temperature=0,
        ),
    )
    if not response.text:
        raise CaseboardError("Gemini returned an empty reading")
    batch = _Batch.model_validate_json(response.text)
    allowed = {item.lower(): item for item in CATEGORIES}
    wanted = {item["id"] for item in chunk}
    rows = []
    for item in batch.items:
        if item.id not in wanted:
            continue
        category = allowed.get(item.category.strip().lower(), "Treatment")
        line = " ".join(item.line.split())[:90]
        if not line:
            continue
        rows.append((item.id, ItemGlance(id=item.id, category=category, line=line, urgent=item.urgent)))
    return rows
