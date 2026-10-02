"""One generated sentence for the top of the firm home."""

import re

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict

from caseboard.domain.enums import DocType
from caseboard.domain.models import CaseSummary, Finding, ItemGlance, TimelineEvent
from caseboard.errors import CaseboardError
from caseboard.glance.text import glance_key
from caseboard.store.documents import DocumentStore
from caseboard.store.upstash import UpstashDocumentStore
from caseboard.validate.critical import CRITICAL_GLANCE

Store = DocumentStore | UpstashDocumentStore
_WORDS = 32
_ACTION_WORDS = 6
_ADDRESSED = re.compile(r"\b(you|your|you're|we|our)\b", re.IGNORECASE)

_PROMPT = """
Write one sentence for the top of a case file.
State the contradicted facts and the items still open, as facts.
At most 32 words.
Do not address the reader. Do not use you, your, we, or our.
Do not restate the client's name, the index numbers, or the accident date.
Do not count the notes. Do not copy a claim number, Social Security number, or policy number.
Use only the notes. Do not invent facts.
Also name up to two short actions a lawyer would open next.
Each action is six words or fewer and must name a concrete item from the notes.
""".strip()


class _Line(BaseModel):
    model_config = ConfigDict(extra="ignore")

    line: str = ""
    actions: list[str] = []


def write_summary(store: Store, api_key: str, model: str) -> str:
    """Replace the stored case sentence from the open conflicts and urgent notes."""
    if not api_key.strip():
        raise CaseboardError("GEMINI_API_KEY is not set")
    notes = summary_notes(store)
    if not notes:
        raise CaseboardError("Nothing to summarize yet")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60_000))
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=_Line.model_json_schema(),
        temperature=0,
    )
    parsed = _ask(client, model, [_PROMPT, notes], config)
    line = clip_summary(parsed.line)
    if not line or _ADDRESSED.search(line):
        parsed = _ask(client, model, [_PROMPT, notes, "Rewrite. Do not address the reader."], config)
        line = clip_summary(parsed.line)
    if not line or _ADDRESSED.search(line):
        raise CaseboardError("Gemini returned a summary that addresses the reader")
    actions = _actions(parsed.actions)
    store.put(DocType.summary, "case", CaseSummary(id="case", line=line, actions=actions))
    return line


def summary_notes(store: Store) -> str:
    """Short labels only. Identifier values stay out of the prompt."""
    findings = [Finding.model_validate(row) for row in store.list_type(DocType.validation)]
    open_labels = [
        CRITICAL_GLANCE[item.code]
        for item in findings
        if not item.resolved and item.code in CRITICAL_GLANCE
    ]
    events = {
        glance_key(TimelineEvent.model_validate(row)): TimelineEvent.model_validate(row)
        for row in store.list_type(DocType.timeline_event)
    }
    urgent = []
    for row in store.list_type(DocType.glance):
        glance = ItemGlance.model_validate(row)
        event = events.get(glance.id)
        if glance.urgent and event is not None:
            urgent.append((event.date or "", glance.line))
    urgent.sort(reverse=True)
    lines = ["Open conflicts: " + "; ".join(open_labels)] if open_labels else []
    if urgent:
        lines.append("Needs attention: " + "; ".join(line for _date, line in urgent[:8]))
    return "\n".join(lines)


def clip_summary(line: str) -> str:
    words = line.split()
    if len(words) > _WORDS:
        line = " ".join(words[:_WORDS]).rstrip(".,;") + "."
    return line.strip()


def _ask(client, model: str, contents: list[str], config) -> _Line:
    response = client.models.generate_content(model=model, contents=contents, config=config)
    return _parsed(response)


def _actions(labels: list[str]) -> list[str]:
    kept = []
    for label in labels:
        words = label.split()
        text = " ".join(words[:_ACTION_WORDS]).strip(" .")
        if text and text not in kept:
            kept.append(text)
        if len(kept) == 2:
            break
    return kept


def _parsed(response) -> _Line:
    if response.parsed is not None:
        return _Line.model_validate(response.parsed)
    if not response.text:
        return _Line()
    return _Line.model_validate_json(response.text)
