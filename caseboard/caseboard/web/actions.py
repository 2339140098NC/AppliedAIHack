"""Buttons: extract the corpus, sync Clio, and rerun validations."""

from caseboard.clio.client import ClioClient
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
            extractor = GeminiExtractor(
                self._settings.gemini_api_key,
                self._settings.gemini_model,
            )
            corpus = CorpusExtractor(
                self._store,
                extractor,
                self._settings.corpus_dir,
                self._settings.compress_dir,
            )
            files = corpus.pdfs()
            if not files:
                raise CaseboardError(f"No PDFs in {self._settings.corpus_dir}")
            problems = corpus.run(self._job.update)
            count = ValidationRunner(self._store).run()
            if problems:
                self._job.finish(
                    f"Extracted with {len(problems)} file errors. {count} findings.",
                    error="; ".join(problems),
                )
                return
            self._job.finish(f"Extracted {len(files)} PDFs. {count} findings.")
        except Exception as exc:
            self._job.finish("Extract failed", error=str(exc))

    def sync(self) -> None:
        try:
            saved = ClioSync(self._store, self._clio).run()
            count = ValidationRunner(self._store).run()
            self._job.finish(f"Synced {saved} Clio communications. {count} findings.")
        except Exception as exc:
            self._job.finish("Clio sync failed", error=str(exc))

    def validate(self) -> int:
        if self._job.snapshot()["running"]:
            raise CaseboardError("Wait for the current job to finish")
        return ValidationRunner(self._store).run()
