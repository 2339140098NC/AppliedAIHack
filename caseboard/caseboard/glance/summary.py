"""One generated sentence for the top of the firm home."""

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

_PROMPT = """
Write one sentence a New York personal-injury lawyer can read when opening this file.
At most 32 words. Say what is unsettled and what needs a decision.
Do not restate the client's name, the index numbers, or the accident date.
Do not count the notes. Do not copy a claim number, Social Security number, or policy number.
Use only the notes. Do not invent facts.
""".strip()


class _Line(BaseModel):
    model_config = ConfigDict(extra="ignore")

    line: str = ""


def write_summary(store: Store, api_key: str, model: str) -> str:
    """Replace the stored case sentence from the open conflicts and urgent notes."""
    if not api_key.strip():
        raise CaseboardError("GEMINI_API_KEY is not set")
    notes = summary_notes(store)
    if not notes:
        raise CaseboardError("Nothing to summarize yet")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=60_000))
    response = client.models.generate_content(
        model=model,
        contents=[_PROMPT, notes],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=_Line.model_json_schema(),
            temperature=0,
        ),
    )
    line = clip_summary(_parsed(response))
    if not line:
        raise CaseboardError("Gemini returned an empty summary")
    store.put(DocType.summary, "case", CaseSummary(id="case", line=line))
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


def _parsed(response) -> str:
    if response.parsed is not None:
        return _Line.model_validate(response.parsed).line
    if not response.text:
        return ""
    return _Line.model_validate_json(response.text).line
