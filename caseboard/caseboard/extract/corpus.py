"""Turn a Gemini extract into stored facets, segments, and events."""

from pathlib import Path

from caseboard.domain.enums import DocType
from caseboard.domain.models import PdfExtract
from caseboard.extract.compress import page_count, prepare_pdf
from caseboard.extract.gemini import GeminiExtractor
from caseboard.store.documents import DocumentStore
from caseboard.store.extractions import ExtractionRecords
from caseboard.store.upstash import UpstashDocumentStore

_HIGH_RES_BITS = ("photo-id", "hipaa", "medical-records", "medical-bills")


def high_resolution(filename: str) -> bool:
    """Scans and ID pages need a higher media resolution than text filings."""
    return any(bit in filename.lower() for bit in _HIGH_RES_BITS)


class CorpusExtractor:
    """Extract every PDF in the corpus and replace the PDF-derived documents."""

    def __init__(
        self,
        store: DocumentStore | UpstashDocumentStore,
        extractor: GeminiExtractor | None,
        corpus_dir: Path,
        compress_dir: Path,
    ) -> None:
        self._store = store
        self._records = ExtractionRecords(store)
        self._extractor = extractor
        self._corpus_dir = corpus_dir
        self._compress_dir = compress_dir

    def pdfs(self) -> list[Path]:
        if not self._corpus_dir.is_dir():
            return []
        return sorted(self._corpus_dir.rglob("*.pdf"))

    def run(self, on_progress) -> list[str]:
        files = self.pdfs()
        self.begin()
        problems: list[str] = []
        for index, path in enumerate(files, start=1):
            on_progress(f"Extracting {index}/{len(files)} {path.name}")
            try:
                self.ingest(path, "")
            except Exception as exc:
                problems.append(f"{path.name}: {exc}")
        self.finish()
        return problems

    def begin(self) -> None:
        self._store.delete_type(DocType.source)
        self._store.delete_type(DocType.segment)
        self._store.delete_type(DocType.facet)
        self._store.delete_type(DocType.group)
        self._store.delete_type(DocType.timeline_event, origin="pdf")

    def ingest(self, path: Path, clio_document_id: str) -> None:
        self._one(path, clio_document_id)

    def finish(self) -> None:
        self._rebuild_groups()

    def forget(self, filename: str) -> None:
        """Drop one PDF's extract. Other files stay."""
        self._records.delete(filename)

    def remember(
        self,
        document_id: str,
        version_id: str,
        filename: str,
        extracted: PdfExtract,
    ) -> None:
        """Replace one file's extract. The version id is what the next sync compares."""
        self._records.replace(filename, document_id, version_id, extracted)

    def _one(self, path: Path, clio_document_id: str) -> None:
        if self._extractor is None:
            raise RuntimeError("PDF extraction is not configured")
        prepared = prepare_pdf(path, self._compress_dir)
        high = high_resolution(path.name)
        extracted = self._extractor.extract_pdf(prepared, high_resolution=high)
        self._records.replace(
            path.name,
            clio_document_id,
            "",
            extracted,
            page_count=page_count(path),
        )

    def _rebuild_groups(self) -> None:
        self._records.rebuild()
