"""One generated sentence for the top of the firm home."""

import re

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict

from caseboard.domain.enums import DocType
from caseboard.domain.models import CaseSummary, Facet, Finding, ItemGlance, TimelineEvent
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
Write two sentences for the top of a case file, plus up to two short actions.
overview: what this case is. One sentence, at most 32 words, from the case sketch only.
Name the incident and the injuries or treatment the file is about.
Do not turn a one-sided injury into both sides.
line: the action in front of the lawyer now. One sentence, at most 32 words, from the open items only.
State the contradicted facts and what is still open.
actions: up to two labels, six words or fewer, each naming a concrete open item.
Do not address the reader. Do not use you, your, we, or our.
Do not restate the client's name, the index numbers, or the accident date.
Do not copy a street address, claim number, Social Security number, or policy number.
Use only the notes. Do not invent facts.
""".strip()


class _Line(BaseModel):
    model_config = ConfigDict(extra="ignore")

    overview: str = ""
    line: str = ""
    actions: list[str] = []


def write_summary(store: Store, api_key: str, model: str) -> str:
    """Replace the stored case sentence from the open conflicts and urgent notes."""
    if not api_key.strip():
        raise CaseboardError("GEMINI_API_KEY is not set")
    if not summary_notes(store) and not _sketch(store):
        raise CaseboardError("Nothing to summarize yet")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60_000))
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=_Line.model_json_schema(),
        temperature=0,
    )
    notes = _notes(store)
    parsed = _ask(client, model, [_PROMPT, notes], config)
    overview, line = _pair(parsed)
    if not overview or not line or _ADDRESSED.search(overview) or _ADDRESSED.search(line):
        parsed = _ask(client, model, [_PROMPT, notes, "Rewrite. Do not address the reader."], config)
        overview, line = _pair(parsed)
    if not overview or not line or _ADDRESSED.search(overview) or _ADDRESSED.search(line):
        raise CaseboardError("Gemini returned a summary that addresses the reader")
    actions = _actions(parsed.actions)
    store.put(DocType.summary, "case", CaseSummary(id="case", overview=overview, line=line, actions=actions))
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


def _notes(store: Store) -> str:
    parts = []
    sketch = _sketch(store)
    if sketch:
        parts.append("Case sketch:\n" + sketch)
    open_items = summary_notes(store)
    if open_items:
        parts.append("Open items:\n" + open_items)
    return "\n\n".join(parts)


def _sketch(store: Store) -> str:
    """Injuries and treatment only. Addresses and identifiers stay out."""
    seen: set[str] = set()
    rows = []
    for row in store.list_type(DocType.facet):
        facet = Facet.model_validate(row)
        key = facet.facet_key
        if not facet.value or not (key.startswith("injury.") or key.startswith("treatment.")):
            continue
        if key == "injury.imaging_provider" or key in seen:
            continue
        seen.add(key)
        rows.append((key, " ".join(facet.value.split()[:12])))
    rows.sort(key=lambda item: (_sketch_rank(item[0]), item[0]))
    return "\n".join(f"{key}: {value}" for key, value in rows[:8])


def _sketch_rank(key: str) -> int:
    for index, bit in enumerate(("shoulder", "knee", "arthroscopy", "neck", "head", "spine")):
        if bit in key:
            return index
    return 6


def _pair(parsed: _Line) -> tuple[str, str]:
    return clip_summary(parsed.overview), clip_summary(parsed.line)


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
