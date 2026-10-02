"""Extract only the PDFs whose Clio version is not already saved."""

from caseboard.clio.client import ClioClient
from caseboard.clio.documents import diff_pdfs, stored_pdfs
from caseboard.domain.enums import DocType
from caseboard.domain.models import SourceFile
from caseboard.extract.corpus import CorpusExtractor, high_resolution
from caseboard.extract.gemini import GeminiExtractor
from caseboard.store.documents import DocumentStore


class PdfChanges:
    """Compare Clio's list to saved sources and send Gemini the file URL for the rest."""

    def __init__(
        self,
        client: ClioClient,
        store: DocumentStore,
        extractor: GeminiExtractor,
        corpus: CorpusExtractor,
    ) -> None:
        self._client = client
        self._store = store
        self._extractor = extractor
        self._corpus = corpus

    def run(self, on_progress) -> tuple[int, int, int, list[str]]:
        """Return counts of changed, removed, and unchanged PDFs, plus per-file errors."""
        remote = stored_pdfs(self._client.list_documents(self._client.matter_id()))
        saved = [
            SourceFile.model_validate(row) for row in self._store.list_type(DocType.source)
        ]
        changed, removed = diff_pdfs(saved, remote)
        by_id = {item.clio_document_id: item for item in saved if item.clio_document_id}
        for filename in removed:
            on_progress(f"Removed {filename}")
            self._corpus.forget(filename)
        problems: list[str] = []
        for index, item in enumerate(changed, start=1):
            on_progress(f"Extracting {index}/{len(changed)} {item.filename}")
            previous = by_id.get(item.document_id)
            try:
                extracted = self._extractor.extract_url(
                    self._client.file_url(item.document_id),
                    item.filename,
                    high_resolution=high_resolution(item.filename),
                )
                if previous is not None and previous.filename != item.filename:
                    self._corpus.forget(previous.filename)
                self._corpus.remember(
                    item.document_id, item.version_id, item.filename, extracted
                )
            except Exception as exc:
                problems.append(f"{item.filename}: {exc}")
        if changed or removed:
            self._corpus.finish()
        unchanged = len(remote) - len(changed)
        return len(changed), len(removed), unchanged, problems
