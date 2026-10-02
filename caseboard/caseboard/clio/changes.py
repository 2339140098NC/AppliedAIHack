"""Extract only the PDFs whose Clio version is not already saved."""

from caseboard.clio.client import ClioClient
from caseboard.clio.documents import RemotePdf, diff_pdfs, select_extracts, stored_pdfs
from caseboard.domain.enums import DocType
from caseboard.domain.models import SourceFile
from caseboard.extract.corpus import CorpusExtractor, high_resolution
from caseboard.extract.gemini import GeminiExtractor
from caseboard.extract.portrait import is_photo_id, save_portrait
from caseboard.store.documents import DocumentStore


class PdfList:
    """Remember Clio's PDF names. Extraction is a separate step."""

    def __init__(self, client: ClioClient, store: DocumentStore, corpus: CorpusExtractor) -> None:
        self._client = client
        self._store = store
        self._corpus = corpus

    def record(self, on_progress) -> tuple[int, int, int, int]:
        """Return counts of new, removed, unchanged, and updated PDFs. Does not call Gemini."""
        remote, _saved, changed, removed, by_id = _compared(self._client, self._store)
        for filename in removed:
            on_progress(f"Removed {filename}")
            self._corpus.forget(filename)
        new = 0
        updated = 0
        for item in changed:
            if by_id.get(item.document_id) is None:
                on_progress(f"Listed {item.filename}")
                self._store.put(
                    DocType.source,
                    item.filename,
                    SourceFile(filename=item.filename, clio_document_id=item.document_id),
                )
                new += 1
            else:
                updated += 1
        if removed:
            self._corpus.finish()
        unchanged = len(remote) - len(changed)
        return new, len(removed), unchanged, updated


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

    def run(self, on_progress, *, only: str = "", force: bool = False) -> tuple[int, int, int, list[str]]:
        """Return counts of changed, removed, and unchanged PDFs, plus per-file errors."""
        remote, _saved, changed, removed, by_id = _compared(self._client, self._store)
        if only:
            changed, missing = select_extracts(changed, remote, only=only, force=force)
            removed = []
            if missing:
                return 0, 0, 0, [missing]
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
                if is_photo_id(item.filename):
                    save_portrait(self._store, self._client.pdf_bytes(item.document_id), item.filename)
                    on_progress("Saved the client photo")
            except Exception as exc:
                problems.append(f"{item.filename}: {exc}")
        if changed or removed:
            self._corpus.finish()
        unchanged = len(remote) - len(changed)
        return len(changed), len(removed), unchanged, problems


def _compared(
    client: ClioClient, store: DocumentStore
) -> tuple[list[RemotePdf], list[SourceFile], list[RemotePdf], list[str], dict[str, SourceFile]]:
    remote = stored_pdfs(client.list_documents(client.matter_id()))
    saved = [SourceFile.model_validate(row) for row in store.list_type(DocType.source)]
    changed, removed = diff_pdfs(saved, remote)
    by_id = {item.clio_document_id: item for item in saved if item.clio_document_id}
    return remote, saved, changed, removed, by_id
