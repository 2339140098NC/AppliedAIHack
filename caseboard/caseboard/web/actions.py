"""Buttons: extract changed Clio PDFs, sync communications, and rerun validations."""

from caseboard.clio.changes import PdfChanges
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
            changed, removed, unchanged, problems = self._pdf_changes()
            count = ValidationRunner(self._store).run()
            self._job.finish(
                _pdf_message(changed, removed, unchanged, count),
                error="; ".join(problems),
            )
        except Exception as exc:
            self._job.finish("Extract failed", error=str(exc))

    def sync(self) -> None:
        try:
            communications = ClioSync(self._store, self._clio).run(self._job.update)
            changed, removed, unchanged, problems = self._pdf_changes()
            count = ValidationRunner(self._store).run()
            self._job.finish(
                f"Stored {communications} records. "
                + _pdf_message(changed, removed, unchanged, count),
                error="; ".join(problems),
            )
        except Exception as exc:
            self._job.finish("Clio sync failed", error=str(exc))

    def validate(self) -> int:
        if self._job.snapshot()["running"]:
            raise CaseboardError("Wait for the current job to finish")
        return ValidationRunner(self._store).run()

    def _pdf_changes(self) -> tuple[int, int, int, list[str]]:
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
        return PdfChanges(self._clio, self._store, extractor, corpus).run(self._job.update)


def _pdf_message(changed: int, removed: int, unchanged: int, findings: int) -> str:
    if changed == 0 and removed == 0:
        return f"PDF list unchanged ({unchanged} saved). {findings} findings."
    return (
        f"Extracted {changed} changed PDFs, removed {removed}, "
        f"{unchanged} unchanged. {findings} findings."
    )
