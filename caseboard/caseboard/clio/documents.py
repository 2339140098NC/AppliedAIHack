"""Choose matter PDFs from a Clio document list and diff them against the store."""

from pathlib import Path
from typing import NamedTuple

from caseboard.domain.models import SourceFile


class RemotePdf(NamedTuple):
    document_id: str
    version_id: str
    filename: str


def stored_pdfs(documents: list[dict]) -> list[RemotePdf]:
    """Return uploaded PDFs, skipping duplicate names."""
    taken: set[str] = set()
    chosen: list[RemotePdf] = []
    for item in documents:
        filename = _pdf_name(item, taken)
        if filename is None:
            continue
        taken.add(filename)
        version = item.get("latest_document_version") or {}
        chosen.append(
            RemotePdf(str(item.get("id")), str(version.get("id") or ""), filename)
        )
    return chosen


def diff_pdfs(
    saved: list[SourceFile], remote: list[RemotePdf]
) -> tuple[list[RemotePdf], list[str]]:
    """Return remote PDFs that are new or updated, and saved filenames no longer in Clio."""
    by_id = {item.clio_document_id: item for item in saved if item.clio_document_id}
    remote_ids = {item.document_id for item in remote}
    changed = [
        item
        for item in remote
        if _changed(by_id.get(item.document_id), item)
    ]
    removed = [
        item.filename
        for item in saved
        if item.clio_document_id not in remote_ids
    ]
    return changed, removed


def select_extracts(
    changed: list[RemotePdf],
    remote: list[RemotePdf],
    *,
    only: str = "",
    force: bool = False,
) -> tuple[list[RemotePdf], str]:
    """Pick the PDFs to send to Gemini. A forced file ignores the saved Clio version."""
    if not only:
        return changed, ""
    chosen = [item for item in remote if item.filename == only]
    if not chosen:
        return [], f"{only} is not a PDF on this matter"
    if force:
        return chosen, ""
    return [item for item in changed if item.filename == only], ""


def _changed(current: SourceFile | None, remote: RemotePdf) -> bool:
    if current is None:
        return True
    return current.clio_version_id != remote.version_id or current.filename != remote.filename


def _pdf_name(item: dict, taken: set[str]) -> str | None:
    version = item.get("latest_document_version") or {}
    if version.get("fully_uploaded") is False:
        return None
    filename = Path(str(version.get("filename") or item.get("name") or "")).name
    kind = str(version.get("content_type") or "").lower()
    if kind != "application/pdf" and not filename.lower().endswith(".pdf"):
        return None
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf" if filename else f"{item.get('id')}.pdf"
    if filename in taken:
        filename = f"{item.get('id')}__{filename}"
    return filename
