"""Structured extraction of one PDF with Gemini."""

import time
from pathlib import Path

from google import genai
from google.genai import types

from caseboard.domain.models import PdfExtract
from caseboard.errors import CaseboardError

PROMPT = """
Extract this personal-injury PDF for the matter of Justin Sapini.
Return segments, facets, and timeline events in the schema.

Rules:
- Every facet and event needs a 1-based page and a short quote that is actually on that page.
- If a value is blank, blacked out, or illegible, set value to null and redacted to true.
- Never complete a Social Security number, driver license number, or covered digits.
- Reuse these facet keys when they apply: patient.name, patient.date_of_birth,
  patient.address, patient.ssn, patient.license_number, accident.datetime,
  accident.location, accident.vehicles, case.index_number, injury.<body_part>,
  treatment.<procedure>, damages.amount, benefits.medicaid, benefits.nofault,
  insurance.policy_number, employment.employee_number.
- Omit a facet the document does not state. Do not invent facts.
- Prefer a checkable set of facts over a sentence-by-sentence dump.
- segment kind must be one of: clinical_note, imaging_report, operative_report, bill,
  hipaa_authorization, photo_id, pleading, discovery, correspondence, expert_report,
  incident_report, other.
- event kind must be one of: accident, treatment, imaging, surgery, filing,
  correspondence, exam, demand.
- Dates use YYYY-MM-DD when the page states a full date.
""".strip()


class GeminiExtractor:
    """Uploads one PDF and returns a schema-constrained extract."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key.strip():
            raise CaseboardError("GEMINI_API_KEY is not set")
        self._model = model
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=600_000),
        )

    def extract_url(self, file_uri: str, filename: str, *, high_resolution: bool) -> PdfExtract:
        """Read a PDF from a URL Gemini can fetch. Nothing is uploaded or stored."""
        response = self._client.models.generate_content(
            model=self._model,
            contents=[
                types.Part.from_uri(file_uri=file_uri, mime_type="application/pdf"),
                PROMPT,
            ],
            config=_config(high_resolution),
        )
        return _parsed(response, filename)

    def extract_pdf(self, path: Path, *, high_resolution: bool) -> PdfExtract:
        uploaded = self._client.files.upload(file=str(path))
        try:
            ready = self._wait(uploaded)
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_uri(
                        file_uri=ready.uri,
                        mime_type="application/pdf",
                    ),
                    PROMPT,
                ],
                config=_config(high_resolution),
            )
            return _parsed(response, path.name)
        finally:
            if uploaded.name:
                self._client.files.delete(name=uploaded.name)

    def _wait(self, uploaded: types.File) -> types.File:
        current = uploaded
        state = getattr(current, "state", None)
        while state is not None and getattr(state, "name", "") == "PROCESSING":
            time.sleep(2)
            current = self._client.files.get(name=current.name)
            state = getattr(current, "state", None)
        if state is not None and getattr(state, "name", "") == "FAILED":
            raise CaseboardError("Gemini could not read the uploaded PDF")
        if not current.uri:
            raise CaseboardError("Gemini did not return a file URI")
        return current


def _config(high_resolution: bool) -> types.GenerateContentConfig:
    resolution = (
        types.MediaResolution.MEDIA_RESOLUTION_HIGH
        if high_resolution
        else types.MediaResolution.MEDIA_RESOLUTION_MEDIUM
    )
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=PdfExtract.model_json_schema(),
        media_resolution=resolution,
        temperature=0,
    )


def _parsed(response: types.GenerateContentResponse, filename: str) -> PdfExtract:
    if response.parsed is not None:
        return PdfExtract.model_validate(response.parsed)
    if not response.text:
        raise CaseboardError(f"Gemini returned an empty extract for {filename}")
    return PdfExtract.model_validate_json(response.text)
