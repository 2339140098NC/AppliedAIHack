"""Clio PDF names are chosen without calling Clio."""

from pathlib import Path

from caseboard.clio.documents import MatterPdfs, stored_pdfs
from caseboard.domain.enums import DocType
from caseboard.store.documents import DocumentStore


def test_stored_pdfs_keep_uploaded_pdfs_only() -> None:
    documents = [
        {"id": 1, "latest_document_version": {"filename": "hipaa.pdf", "content_type": "application/pdf", "fully_uploaded": True}},
        {"id": 2, "latest_document_version": {"filename": "notes.docx", "content_type": "application/vnd.openxmlformats", "fully_uploaded": True}},
        {"id": 3, "latest_document_version": {"filename": "draft.pdf", "content_type": "application/pdf", "fully_uploaded": False}},
        {"id": 4, "name": "photo-id.pdf", "latest_document_version": {"filename": "hipaa.pdf", "content_type": "application/pdf", "fully_uploaded": True}},
    ]
    assert stored_pdfs(documents) == [
        ("1", "hipaa.pdf"),
        ("4", "4__hipaa.pdf"),
    ]


def test_catalog_records_ids_without_downloading(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")

    class FakeClient:
        def list_documents(self, matter_id: str) -> list[dict]:
            assert matter_id == "1811189963"
            return [
                {
                    "id": 9,
                    "latest_document_version": {
                        "filename": "letter.pdf",
                        "content_type": "application/pdf",
                        "fully_uploaded": True,
                    },
                }
            ]

        def download_pdf(self, document_id: str, dest: Path) -> None:
            raise AssertionError("catalog must not download")

    saved = MatterPdfs(FakeClient(), store).catalog("1811189963")
    assert saved == 1
    rows = store.list_type(DocType.source)
    assert rows[0]["filename"] == "letter.pdf"
    assert rows[0]["clio_document_id"] == "9"
    assert rows[0]["page_count"] == 0
