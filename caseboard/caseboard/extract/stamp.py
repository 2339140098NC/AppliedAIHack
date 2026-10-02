"""Identity of the current extract instructions. A change marks saved PDFs out of date."""

import hashlib
import json

from caseboard.domain.models import PdfExtract
from caseboard.extract.gemini import PROMPT


def extract_stamp() -> str:
    """Short hash of the prompt and the response schema."""
    body = PROMPT + "\n" + json.dumps(PdfExtract.model_json_schema(), sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:12]
