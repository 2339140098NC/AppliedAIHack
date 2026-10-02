"""Read dollar amounts off medical bills without touching the fact extract."""

import hashlib
import re

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from caseboard.clio.client import ClioClient
from caseboard.domain.enums import DocType, SegmentKind
from caseboard.domain.models import Charge, Segment, SourceFile
from caseboard.errors import CaseboardError
from caseboard.extract.corpus import high_resolution
from caseboard.store.documents import DocumentStore
from caseboard.store.upstash import UpstashDocumentStore

Store = DocumentStore | UpstashDocumentStore

_PROMPT = """
Read this medical bill for a New York personal-injury file.
Return the biller and the dollar amounts the page actually prints.

- provider: the practice or facility that billed. Use a short name.
- lines: at most 12. If the page states a total, balance, or amount due, include that line. Include itemized rows only when the bill has 6 or fewer of them.
- amount: copy the printed figure, including the dollar sign. Do not add, round, or compute a total.
- description: the service name, or Total, Balance, or Amount due when that is the figure.
- service_date: YYYY-MM-DD when a full date is printed, otherwise empty.
- page: the 1-based page of the quote.
- quote: a short span from that page that contains the amount.

Omit payments, adjustments, write-offs, and any line with no dollar amount.
Do not invent a total the page does not state.
""".strip()


class BillLine(BaseModel):
    """One printed figure inside a bill reading."""

    model_config = ConfigDict(extra="ignore")

    provider: str = ""
    description: str = ""
    amount: str = ""
    service_date: str = ""
    page: int = 1
    quote: str = ""


class BillRead(BaseModel):
    """Gemini's reading of one bill PDF."""

    model_config = ConfigDict(extra="ignore")

    provider: str = ""
    lines: list[BillLine] = Field(default_factory=list)


def read_bills(
    store: Store,
    clio: ClioClient,
    api_key: str,
    model: str,
    on_progress,
    *,
    only: set[str] | None = None,
) -> int:
    """Replace stored charges from the matter's bill PDFs. Other extracts stay."""
    if not api_key.strip():
        raise CaseboardError("GEMINI_API_KEY is not set")
    sources = _bill_sources(store)
    if only is not None:
        sources = [source for source in sources if source.filename in only]
    if not sources:
        raise CaseboardError("No medical bills are on this matter yet")
    client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=180_000))
    rows: list[tuple[str, Charge]] = []
    problems: list[str] = []
    for index, source in enumerate(sources, start=1):
        on_progress(f"Reading bill {index}/{len(sources)}")
        if not source.clio_document_id:
            problems.append(f"{source.filename}: no Clio file")
            continue
        try:
            found = _read_one(client, model, clio, source)
            if not found:
                problems.append(f"{source.filename}: no printed amount")
            rows.extend((item.id, item) for item in found)
        except Exception as exc:
            problems.append(f"{source.filename}: {exc}")
    for problem in problems:
        on_progress(problem)
    if not rows and only is None:
        raise CaseboardError("; ".join(problems) or "No amounts were printed on the bills")
    _save(store, rows, only)
    return len(rows)


def charges_from(filename: str, read: BillRead) -> list[Charge]:
    """Keep copied amounts. Drop blanks and anything past the glance cap."""
    provider = _clip(read.provider, 80) or "Unnamed biller"
    kept = _prefer_totals(read.lines)[:12]
    rows = []
    for line in kept:
        amount = _clip(line.amount, 24)
        if not re.search(r"\d", amount):
            continue
        description = _clip(line.description, 80) or "Charge"
        name = _clip(line.provider, 80) or provider
        page = line.page if line.page > 0 else 1
        quote = _clip(line.quote, 240)
        rows.append(
            Charge(
                id=_charge_id(filename, page, amount, description),
                provider=name,
                description=description,
                amount=amount,
                service_date=_date(line.service_date),
                document=filename,
                page=page,
                quote=quote,
            )
        )
    return rows


def _bill_sources(store: Store) -> list[SourceFile]:
    names = {
        segment.source_file
        for segment in (Segment.model_validate(row) for row in store.list_type(DocType.segment))
        if segment.kind == SegmentKind.bill
    }
    found = []
    seen: set[str] = set()
    for row in store.list_type(DocType.source):
        source = SourceFile.model_validate(row)
        if source.filename in names or "medical-bills" in source.filename.lower():
            if source.filename not in seen:
                seen.add(source.filename)
                found.append(source)
    found.sort(key=lambda item: item.filename)
    return found


_RETRY = """
Look again at this medical bill. The first pass found no dollar amount.
Return up to 8 lines that contain a printed dollar figure: a total, a balance, or itemized charges.
Copy each figure, including the dollar sign. Do not add or invent a total.
If the page truly shows no dollar amount, return an empty lines list.
""".strip()


def _read_one(client: genai.Client, model: str, clio: ClioClient, source: SourceFile) -> list[Charge]:
    file_uri = clio.file_url(source.clio_document_id)
    read = _ask(client, model, file_uri, source.filename, _PROMPT)
    found = charges_from(source.filename, read)
    if found:
        return found
    file_uri = clio.file_url(source.clio_document_id)
    read = _ask(client, model, file_uri, source.filename, _RETRY)
    return charges_from(source.filename, read)


def _save(store: Store, rows: list[tuple[str, Charge]], only: set[str] | None) -> None:
    if only is None:
        store.delete_type(DocType.charge)
    else:
        stale = [
            str(row["id"])
            for row in store.list_type(DocType.charge)
            if str(row.get("document") or "") in only
        ]
        store.delete_ids(DocType.charge, stale)
    store.put_many(DocType.charge, rows)


def _ask(client: genai.Client, model: str, file_uri: str, filename: str, prompt: str) -> BillRead:
    response = client.models.generate_content(
        model=model,
        contents=[
            types.Part.from_uri(file_uri=file_uri, mime_type="application/pdf"),
            prompt,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=BillRead.model_json_schema(),
            media_resolution=(
                types.MediaResolution.MEDIA_RESOLUTION_HIGH
                if high_resolution(filename)
                else types.MediaResolution.MEDIA_RESOLUTION_MEDIUM
            ),
            temperature=0,
        ),
    )
    if response.parsed is not None:
        return BillRead.model_validate(response.parsed)
    if not response.text:
        raise CaseboardError(f"Gemini returned an empty bill reading for {filename}")
    return BillRead.model_validate_json(response.text)


def _prefer_totals(lines: list[BillLine]) -> list[BillLine]:
    totals = [line for line in lines if _is_total(line.description)]
    rest = [line for line in lines if line not in totals]
    if totals and len(rest) > 6:
        return totals
    return totals + rest


def _is_total(description: str) -> bool:
    text = description.lower()
    return any(bit in text for bit in ("total", "balance", "amount due"))


def _charge_id(filename: str, page: int, amount: str, description: str) -> str:
    raw = f"{filename}|{page}|{amount}|{description}".lower()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _clip(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


def _date(value: str) -> str:
    text = value.strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return ""
