"""Buttons: extract Clio PDFs, sync communications, and rerun validations."""

import tempfile
from pathlib import Path

from caseboard.clio.client import ClioClient
from caseboard.clio.documents import stored_pdfs
from caseboard.clio.sync import ClioSync
from caseboard.config import Settings
from caseboard.errors import CaseboardError
from caseboard.extract.corpus import CorpusExtractor
from caseboard.extract.gemini import GeminiExtractor
from caseboard.store.documents import DocumentStore
from caseboard.validate.runner import ValidationRunner
from caseboard.web.jobs import Job


class Actions:
    def __init__(
        self,
        settings: Settings,
        store: DocumentStore,
        clio: ClioClient,
        job: Job,
    ) -> None:
        self._settings = settings
        self._store = store
        self._clio = clio
        self._job = job

    def extract(self) -> None:
        try:
            chosen = stored_pdfs(self._clio.list_documents(self._clio.matter_id()))
            if not chosen:
                raise CaseboardError("Clio has no PDFs for this matter.")
            extractor = GeminiExtractor(
                self._settings.gemini_api_key,
                self._settings.gemini_model,
            )
            corpus = CorpusExtractor(
                self._store,
                extractor,
                self._settings.docs_dir,
                self._settings.compress_dir,
            )
            corpus.begin()
            problems = self._extract_each(corpus, chosen)
            corpus.finish()
            count = ValidationRunner(self._store).run()
            if problems:
                self._job.finish(
                    f"Extracted with {len(problems)} file errors. {count} findings.",
                    error="; ".join(problems),
                )
                return
            self._job.finish(f"Extracted {len(chosen)} PDFs from Clio. {count} findings.")
        except Exception as exc:
            self._job.finish("Extract failed", error=str(exc))

    def _extract_each(self, corpus: CorpusExtractor, chosen: list[tuple[str, str]]) -> list[str]:
        problems: list[str] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for index, (document_id, filename) in enumerate(chosen, start=1):
                self._job.update(f"Extracting {index}/{len(chosen)} {filename}")
                dest = root / filename
                try:
                    self._clio.download_pdf(document_id, dest)
                    corpus.ingest(dest, document_id)
                except Exception as exc:
                    problems.append(f"{filename}: {exc}")
        return problems

    def sync(self) -> None:
        try:
            communications, pdfs = ClioSync(self._store, self._clio).run(self._job.update)
            count = ValidationRunner(self._store).run()
            self._job.finish(
                f"Listed {pdfs} Clio PDFs and stored {communications} records. {count} findings."
            )
        except Exception as exc:
            self._job.finish("Clio sync failed", error=str(exc))

    def validate(self) -> int:
        if self._job.snapshot()["running"]:
            raise CaseboardError("Wait for the current job to finish")
        return ValidationRunner(self._store).run()
