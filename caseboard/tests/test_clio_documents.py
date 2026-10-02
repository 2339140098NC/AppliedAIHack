"""Clio PDF names are chosen without calling Clio."""

from pathlib import Path

import pymupdf as fitz

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


def test_pull_writes_source_rows(tmp_path: Path) -> None:
    store = DocumentStore(tmp_path / "case.sqlite")
    docs = tmp_path / "pdfs"

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
            assert document_id == "9"
            document = fitz.open()
            document.new_page()
            document.save(dest)
            document.close()

    messages: list[str] = []
    saved = MatterPdfs(FakeClient(), store, docs).pull("1811189963", messages.append)
    assert saved == 1
    assert (docs / "letter.pdf").is_file()
    rows = store.list_type(DocType.source)
    assert rows[0]["filename"] == "letter.pdf"
    assert rows[0]["page_count"] == 1
    assert messages == ["Saving PDF 1/1 letter.pdf"]
