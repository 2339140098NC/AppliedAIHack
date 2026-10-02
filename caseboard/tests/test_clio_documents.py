"""Clio PDF names are chosen and diffed without calling Clio."""

from pathlib import Path

from caseboard.clio.changes import PdfList
from caseboard.clio.parties import event_when
from caseboard.clio.documents import RemotePdf, diff_pdfs, select_extracts, stored_pdfs
from caseboard.domain.enums import DocType
from caseboard.domain.models import ModelEvidence, ModelEvent, ModelFacet, ModelSegment, PdfExtract, SourceFile
from caseboard.extract.corpus import CorpusExtractor
from caseboard.store.documents import DocumentStore


def test_stored_pdfs_keep_uploaded_pdfs_only() -> None:
    documents = [
        {
            "id": 1,
            "latest_document_version": {
                "id": 11,
                "filename": "hipaa.pdf",
                "content_type": "application/pdf",
                "fully_uploaded": True,
            },
        },
        {
            "id": 2,
            "latest_document_version": {
                "filename": "notes.docx",
                "content_type": "application/vnd.openxmlformats",
                "fully_uploaded": True,
            },
        },
        {
            "id": 3,
            "latest_document_version": {
                "filename": "draft.pdf",
                "content_type": "application/pdf",
                "fully_uploaded": False,
            },
        },
        {
            "id": 4,
            "name": "photo-id.pdf",
            "latest_document_version": {
                "filename": "hipaa.pdf",
                "content_type": "application/pdf",
                "fully_uploaded": True,
            },
        },
    ]
    assert stored_pdfs(documents) == [
        RemotePdf("1", "11", "hipaa.pdf"),
        RemotePdf("4", "", "4__hipaa.pdf"),
    ]


def test_diff_pdfs_keeps_matching_versions() -> None:
    saved = [
        SourceFile(filename="a.pdf", clio_document_id="1", clio_version_id="v1", page_count=2),
        SourceFile(filename="gone.pdf", clio_document_id="2", clio_version_id="v1"),
        SourceFile(filename="old.pdf", clio_document_id="3", clio_version_id="v1"),
    ]
    remote = [
        RemotePdf("1", "v1", "a.pdf"),
        RemotePdf("3", "v2", "renamed.pdf"),
        RemotePdf("4", "v1", "new.pdf"),
    ]
    changed, removed = diff_pdfs(saved, remote)
    assert removed == ["gone.pdf"]
    assert changed == [
        RemotePdf("3", "v2", "renamed.pdf"),
        RemotePdf("4", "v1", "new.pdf"),
    ]


def test_force_reextract_ignores_the_saved_version() -> None:
    remote = [RemotePdf("1", "v1", "a.pdf"), RemotePdf("2", "v1", "b.pdf")]
    picked, missing = select_extracts([], remote, only="a.pdf", force=True)
    assert missing == ""
    assert picked == [RemotePdf("1", "v1", "a.pdf")]
    picked, missing = select_extracts([], remote, only="missing.pdf", force=True)
    assert picked == []
    assert "missing.pdf" in missing


def test_remember_drops_only_that_file(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    corpus = CorpusExtractor(store, None, tmp_path, tmp_path)  # type: ignore[arg-type]
    extracted = PdfExtract(
        segments=[ModelSegment(page_end=3)],
        facets=[
            ModelFacet(
                facet_key="patient.name",
                value="Justin",
                evidence=[ModelEvidence(page=2, quote="Justin")],
            )
        ],
        events=[ModelEvent(label="Visit", evidence=[ModelEvidence(page=2, quote="Visit")])],
    )
    corpus.remember("9", "v1", "letter.pdf", extracted)
    corpus.remember("8", "v1", "other.pdf", extracted)
    corpus.forget("letter.pdf")
    assert [row["filename"] for row in store.list_type(DocType.source)] == ["other.pdf"]
    facets = store.list_type(DocType.facet)
    assert facets
    assert all(cite["document"] == "other.pdf" for row in facets for cite in row["evidence"])


def test_sync_lists_pdfs_without_fetching_them(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")

    class FakeClient:
        def matter_id(self) -> str:
            return "1811189963"

        def list_documents(self, matter_id: str) -> list[dict]:
            return [
                {
                    "id": 9,
                    "latest_document_version": {
                        "id": 3,
                        "filename": "letter.pdf",
                        "content_type": "application/pdf",
                        "fully_uploaded": True,
                    },
                }
            ]

        def file_url(self, document_id: str) -> str:
            raise AssertionError("listing must not fetch a file")

    corpus = CorpusExtractor(store, None, tmp_path, tmp_path)
    new, removed, unchanged, updated = PdfList(FakeClient(), store, corpus).record(lambda _message: None)
    assert (new, removed, unchanged, updated) == (1, 0, 0, 0)
    row = store.list_type(DocType.source)[0]
    assert row["filename"] == "letter.pdf"
    assert row["clio_document_id"] == "9"
    assert row["clio_version_id"] == ""


def test_save_time_does_not_replace_the_communication_date() -> None:
    day, clock = event_when("2023-05-07", None)
    assert day == "2023-05-07"
    assert clock == ""
    day, clock = event_when("2023-05-07", "2023-05-07T14:14:00Z")
    assert day == "2023-05-07"
    assert clock == "2:14 PM"
