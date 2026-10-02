"""Buttons: extract changed Clio PDFs, sync communications, and rerun validations."""

from caseboard.clio.changes import PdfChanges, PdfList
from caseboard.clio.client import ClioClient
from caseboard.clio.sync import ClioSync
from caseboard.config import Settings
from caseboard.errors import CaseboardError
from caseboard.extract.bills import read_bills
from caseboard.extract.corpus import CorpusExtractor
from caseboard.extract.gemini import GeminiExtractor
from caseboard.glance.classify import classify_timeline
from caseboard.glance.summary import write_summary
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

    def extract_one(self, filename: str) -> None:
        try:
            changed, removed, unchanged, problems = self._pdf_changes(only=filename, force=True)
            count = ValidationRunner(self._store).run()
            self._job.finish(
                _pdf_message(changed, removed, unchanged, count),
                error="; ".join(problems),
            )
        except Exception as exc:
            self._job.finish("Extract failed", error=str(exc))

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
            new, removed, unchanged, updated = self._note_pdfs()
            count = ValidationRunner(self._store).run()
            self._job.finish(
                f"Stored {communications} records. "
                + _list_message(new, removed, unchanged, updated, count)
            )
        except Exception as exc:
            self._job.finish("Clio sync failed", error=str(exc))

    def glance(self) -> None:
        """Read the stored timeline text and write a one-line category for each item."""
        try:
            count = classify_timeline(
                self._store,
                self._settings.gemini_api_key,
                self._settings.gemini_model,
                self._job.update,
            )
            self._job.update("Writing the case summary")
            write_summary(self._store, self._settings.gemini_api_key, self._settings.gemini_model)
            self._job.finish(f"Read {count} timeline items.")
        except Exception as exc:
            self._job.finish("Reading the timeline failed", error=str(exc))

    def bills(self) -> None:
        """Read printed amounts off the medical bills. The fact extract is left alone."""
        try:
            count = read_bills(
                self._store,
                self._clio,
                self._settings.gemini_api_key,
                self._settings.gemini_model,
                self._job.update,
            )
            self._job.finish(f"Read {count} bill amounts.")
        except Exception as exc:
            self._job.finish("Reading the bills failed", error=str(exc))

    def validate(self) -> int:
        if self._job.snapshot()["running"]:
            raise CaseboardError("Wait for the current job to finish")
        return ValidationRunner(self._store).run()

    def _note_pdfs(self) -> tuple[int, int, int, int]:
        corpus = CorpusExtractor(
            self._store,
            None,
            self._settings.docs_dir,
            self._settings.compress_dir,
        )
        return PdfList(self._clio, self._store, corpus).record(self._job.update)

    def _pdf_changes(self, *, only: str = "", force: bool = False) -> tuple[int, int, int, list[str]]:
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
        return PdfChanges(self._clio, self._store, extractor, corpus).run(
            self._job.update, only=only, force=force
        )


def _list_message(new: int, removed: int, unchanged: int, updated: int, findings: int) -> str:
    if new == 0 and removed == 0 and updated == 0:
        return f"PDF list unchanged ({unchanged} saved). {findings} findings."
    return (
        f"{new} new PDFs, {updated} updated, {removed} removed, "
        f"{unchanged} unchanged. {findings} findings."
    )


def _pdf_message(changed: int, removed: int, unchanged: int, findings: int) -> str:
    if changed == 0 and removed == 0:
        return f"PDF list unchanged ({unchanged} saved). {findings} findings."
    return (
        f"Extracted {changed} changed PDFs, removed {removed}, "
        f"{unchanged} unchanged. {findings} findings."
    )
