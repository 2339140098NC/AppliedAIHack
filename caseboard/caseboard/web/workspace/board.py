"""Assemble the workspace from the document store."""

from calendar import month_abbr
from pathlib import Path

from caseboard.domain.enums import DocType, GroupStatus, Sensitivity
from caseboard.domain.models import (
    ComparisonGroup,
    Facet,
    Finding,
    Segment,
    SourceFile,
    TimelineEvent,
)
from caseboard.store.documents import DocumentStore
from caseboard.web.workspace.query import PROVIDERS, WorkspaceQuery

_MONTHS = [name.upper() for name in month_abbr if name]
_KIND = {"call": "Phone", "email": "Email", "note": "Note", "message": "Message"}
_CLINICAL = {"clinical_note", "imaging_report", "operative_report", "bill"}
_SECTIONS = (
    ("sensitive", "Before sharing anything", "Things a provider must never see, or that must be fixed first."),
    ("conflict", "Facts that disagree", "Documents say different things. Decide which is right; don’t smooth it over."),
    ("incomplete", "Missing or blank", "Fields left empty, or papers the file mentions but doesn’t contain."),
)


class Workspace:
    """One render of the firm or provider workspace."""

    def __init__(self, store: DocumentStore, query: WorkspaceQuery) -> None:
        self.query = query
        self.sources = [SourceFile.model_validate(row) for row in store.list_type(DocType.source)]
        self.segments = [Segment.model_validate(row) for row in store.list_type(DocType.segment)]
        self.facets = [Facet.model_validate(row) for row in store.list_type(DocType.facet)]
        self.groups = [ComparisonGroup.model_validate(row) for row in store.list_type(DocType.group)]
        self.events = [TimelineEvent.model_validate(row) for row in store.list_type(DocType.timeline_event)]
        self.findings = [Finding.model_validate(row) for row in store.list_type(DocType.validation)]
        self._conflict_pages = {
            (cite.document, cite.page)
            for group in self.groups
            if group.status == GroupStatus.conflict
            for entry in group.entries
            for cite in entry.evidence
        }

    def context(self) -> dict:
        query = self._with_viewer()
        findings = self._findings()
        open_items = [item for item in findings if not item["done"]]
        return {
            "query": query,
            "firm": query.firm,
            "provider_name": query.provider_name(),
            "providers": [(key, name) for key, name, _tokens in PROVIDERS],
            "plate": self._plate(len(open_items)),
            "tabs": self._tabs(len(open_items)),
            "years": self._years(query),
            "groups": self._groups(query),
            "facts": self._facts(query),
            "findings": findings,
            "open_count": len(open_items),
            "finding_count": len(findings),
            "sections": _SECTIONS,
            "records": self._records(query),
            "viewer": self._viewer(query),
            "ev_compared": query.ev != "all",
        }

    def _with_viewer(self) -> WorkspaceQuery:
        query = self.query
        if query.document:
            return query
        if query.firm and self.sources:
            return WorkspaceQuery(
                view=query.view,
                provider=query.provider,
                tab=query.tab,
                document=self.sources[0].filename,
                page=1,
                quote="",
                ev=query.ev,
                selected="",
            )
        owned = self._owned_segments(query.provider)
        if not query.firm and owned:
            first = owned[0]
            return WorkspaceQuery(
                view=query.view,
                provider=query.provider,
                tab=query.tab,
                document=first.source_file,
                page=first.page_start,
                quote="",
                ev=query.ev,
                selected="",
            )
        return query

    def _plate(self, open_count: int) -> list[dict]:
        pages = sum(item.page_count for item in self.sources)
        files = len(self.sources)
        if not files:
            file_label = "No PDFs yet"
        elif pages:
            noun = "PDF" if files == 1 else "PDFs"
            file_label = f"{files} {noun} · {pages} pp."
        else:
            noun = "PDF" if files == 1 else "PDFs"
            file_label = f"{files} {noun}"
        cells = [
            {"k": "Client", "v": self._value("patient.name") or "Justin Sapini"},
            {"k": "Index", "v": self._value("case.index_number") or "160000/2024"},
            {"k": "Accident", "v": _pretty_date(self._value("accident.datetime") or self._value("accident.date")) or "Apr 23, 2023"},
            {"k": "Files", "v": file_label},
        ]
        if self.query.firm:
            cells.append({"k": "Open to-dos", "v": str(open_count), "live": open_count > 0})
        else:
            owned = self._owned_segments(self.query.provider)
            cells = [
                {"k": "Client", "v": "Justin Sapini"},
                {"k": "Records", "v": f"{len(owned)} document{'s' if len(owned) != 1 else ''}"},
            ]
        return cells

    def _tabs(self, open_count: int) -> list[dict]:
        if self.query.firm:
            specs = [("timeline", "Timeline", None), ("evidence", "Evidence", None), ("todo", "To-do", open_count or None)]
        else:
            specs = [("timeline", "Timeline", None), ("records", "My records", None)]
        tabs = []
        for index, (tab, label, count) in enumerate(specs, start=1):
            tabs.append({
                "num": f"{index:02d}",
                "label": label,
                "count": count,
                "active": self.query.tab == tab,
                "href": self.query.url(tab=tab, document="", page="", quote="", sel=""),
            })
        return tabs

    def _years(self, query: WorkspaceQuery) -> list[dict]:
        events = self._visible_events(query)
        events.sort(key=lambda item: (item.date is None, "" if item.date else item.date), reverse=False)
        dated = [item for item in events if item.date]
        undated = [item for item in events if not item.date]
        dated.sort(key=lambda item: item.date or "", reverse=True)
        groups: list[dict] = []
        for event in dated + undated:
            label = event.date[:4] if event.date else "Undated"
            if not groups or groups[-1]["label"] != label:
                groups.append({"label": label, "events": []})
            groups[-1]["events"].append(self._event_row(event, query))
        for group in groups:
            count = len(group["events"])
            group["count"] = f"{count} event" if count == 1 else f"{count} events"
        return groups

    def _visible_events(self, query: WorkspaceQuery) -> list[TimelineEvent]:
        if query.firm:
            return list(self.events)
        return [event for event in self.events if self._provider_event(event, query.provider)]

    def _event_row(self, event: TimelineEvent, query: WorkspaceQuery) -> dict:
        evidence = event.evidence[0] if event.evidence else None
        document = evidence.document if evidence else ""
        page = evidence.page if evidence else 1
        quote = evidence.quote if evidence else ""
        conflict = any((cite.document, cite.page) in self._conflict_pages for cite in event.evidence)
        month, day = _month_day(event.date)
        who = _provider_name(_blob(event.label, event.sensitivity_reason, document, quote))
        kind = _KIND.get(event.kind.value, event.kind.value.replace("_", " ").title())
        if query.firm and who:
            kind = f"{kind} · {who}"
        return {
            "id": event.id,
            "month": month,
            "day": day,
            "kind": kind,
            "label": event.label,
            "sub": event.time or "",
            "src": self._source_label(document, page, query),
            "href": query.url(document=document, page=page, quote=quote, sel=event.id) if document else "",
            "selected": query.selected == event.id,
            "conflict": query.firm and conflict,
            "sensitive": query.firm and event.sensitivity == Sensitivity.firm_only and _sensitive(event.label, event.sensitivity_reason),
            "incomplete": query.firm and not event.date,
            "incomplete_label": "Dates not extracted" if not event.date else "",
            "show_vis": query.firm,
            "firm_only": event.sensitivity == Sensitivity.firm_only,
            "vis_label": "Firm only" if event.sensitivity == Sensitivity.firm_only else f"Shared with {who or 'providers'}",
        }

    def _groups(self, query: WorkspaceQuery) -> list[dict]:
        cards = []
        for group in self.groups:
            entries = [entry for entry in group.entries if query.firm or entry.sensitivity == Sensitivity.provider_visible]
            if not entries:
                continue
            rows = []
            for index, entry in enumerate(entries):
                evidence = entry.evidence[0] if entry.evidence else None
                rows.append({
                    "letter": "ABCDEFGHIJ"[index] if len(entries) > 1 else "·",
                    "value": entry.value or "Left blank",
                    "blank": not entry.value,
                    "conflict": group.status == GroupStatus.conflict,
                    "sources": [
                        {
                            "label": self._source_label(cite.document, cite.page, query),
                            "href": query.url(document=cite.document, page=cite.page, quote=cite.quote, sel=group.id, tab="evidence"),
                        }
                        for cite in entry.evidence
                        if cite.document
                    ],
                })
            cards.append({
                "id": group.id,
                "title": _title(group.facet_key),
                "selected": query.selected == group.id,
                "conflict": group.status == GroupStatus.conflict,
                "incomplete": group.status == GroupStatus.incomplete,
                "consistent": group.status == GroupStatus.consistent and len(entries) > 1,
                "single": group.status == GroupStatus.consistent and len(entries) == 1,
                "sensitive": all(entry.sensitivity == Sensitivity.firm_only for entry in entries) and _sensitive(group.facet_key, ""),
                "rows": rows,
            })
        return cards

    def _facts(self, query: WorkspaceQuery) -> list[dict]:
        rows = []
        for facet in self.facets:
            if not query.firm and facet.sensitivity != Sensitivity.provider_visible:
                continue
            evidence = facet.evidence[0] if facet.evidence else None
            if not evidence:
                continue
            who = "Firm only"
            if facet.sensitivity == Sensitivity.provider_visible:
                who = _provider_name(_blob(facet.authored_by, facet.facet_key, evidence.document)) or "Shared"
            rows.append({
                "fact": _title(facet.facet_key),
                "value": facet.value or "Left blank",
                "src": self._source_label(evidence.document, evidence.page, query),
                "vis": who,
                "href": query.url(document=evidence.document, page=evidence.page, quote=evidence.quote, sel=facet.id, tab="evidence", ev="all"),
            })
        return rows

    def _findings(self) -> list[dict]:
        rows = []
        for finding in sorted(self.findings, key=lambda item: item.message):
            evidence = finding.evidence[0] if finding.evidence else None
            title, _, detail = finding.message.partition(". ")
            rows.append({
                "id": finding.id,
                "severity": finding.severity.value,
                "title": title,
                "detail": detail or finding.code,
                "done": finding.resolved,
                "src": self._source_label(evidence.document, evidence.page, self.query) if evidence else "",
                "href": self.query.url(document=evidence.document, page=evidence.page, quote=evidence.quote, sel=finding.id, tab="todo") if evidence else "",
            })
        return rows

    def _records(self, query: WorkspaceQuery) -> dict:
        facts = []
        for facet in self.facets:
            if facet.sensitivity != Sensitivity.provider_visible or not facet.value:
                continue
            evidence = facet.evidence[0] if facet.evidence else None
            blob = _blob(facet.authored_by, facet.facet_key, evidence.document if evidence else "", facet.value)
            if not _matches(query.provider, blob):
                continue
            page = evidence.page if evidence else 1
            document = evidence.document if evidence else ""
            facts.append({
                "label": _title(facet.facet_key),
                "value": facet.value,
                "src": self._source_label(document, page, query),
                "href": query.url(document=document, page=page, quote=evidence.quote if evidence else "", tab="records") if document else "",
            })
        documents = []
        for segment in self._owned_segments(query.provider):
            documents.append({
                "label": segment.kind.value.replace("_", " ").title(),
                "pages": _page_span(segment.page_start, segment.page_end),
                "href": query.url(document=segment.source_file, page=segment.page_start, quote="", tab="records"),
            })
        return {"facts": facts, "documents": documents}

    def _viewer(self, query: WorkspaceQuery) -> dict:
        document = query.document
        page = query.page or 1
        if not query.firm:
            owned = self._owned_segments(query.provider)
            allowed = {item.source_file for item in owned}
            if document not in allowed:
                if owned:
                    document = owned[0].source_file
                    page = owned[0].page_start
                else:
                    document = ""
            segment = _segment_at(self.segments, document, page) if document else None
            if segment:
                lo, hi = segment.page_start, segment.page_end
            elif owned:
                lo, hi = owned[0].page_start, owned[0].page_end
                document, page = owned[0].source_file, lo
                segment = owned[0]
            else:
                lo, hi = 1, 1
                document = ""
            page = min(max(page, lo), hi)
            title = segment.kind.value.replace("_", " ").title() if segment else "Record"
            sub = f"{query.provider_name()} · Justin Sapini"
            banner = ""
            show_name = False
        else:
            source = next((item for item in self.sources if item.filename == document), None)
            count = source.page_count if source else page
            lo, hi = 1, max(count, 1)
            page = min(max(page, 1), hi)
            segment = _segment_at(self.segments, document, page)
            title = _title(Path(document).stem.split("__")[-1]) if document else "No page open"
            sub = document
            show_name = True
            banner = ""
            court_file = "__doc-" in document or "nyscef" in document.lower()
            if court_file and segment and (segment.nyscef_doc or segment.nyscef_index):
                banner = f"NYSCEF DOC. NO. {segment.nyscef_doc or '—'} · INDEX NO. {segment.nyscef_index or '—'}"
        chips = []
        if query.firm:
            file_segments = [item for item in self.segments if item.source_file == document]
            if len(file_segments) > 1:
                for item in file_segments:
                    chips.append({
                        "label": item.kind.value.replace("_", " ").title(),
                        "range": _page_span(item.page_start, item.page_end),
                        "active": item.page_start <= page <= item.page_end,
                        "href": query.url(document=document, page=item.page_start, quote=""),
                    })
        quotes = self._quotes(document, page, query)
        return {
            "title": title,
            "sub": sub,
            "banner": banner,
            "show_name": show_name,
            "document": document,
            "page": page,
            "image": bool(document.lower().endswith(".pdf")) if document else False,
            "chips": chips,
            "page_label": f"Page {page - lo + 1} of {hi - lo + 1}",
            "prev": query.url(document=document, page=max(lo, page - 1), quote=""),
            "next": query.url(document=document, page=min(hi, page + 1), quote=""),
            "seg_label": segment.kind.value.replace("_", " ").title() if segment else "Page",
            "quotes": quotes,
            "footer": str(page - lo + 1),
        }

    def _quotes(self, document: str, page: int, query: WorkspaceQuery) -> list[dict]:
        found: list[dict] = []
        seen: set[str] = set()
        for facet in self.facets:
            if not query.firm and facet.sensitivity != Sensitivity.provider_visible:
                continue
            for cite in facet.evidence:
                if cite.document != document or cite.page != page or not cite.quote or cite.quote in seen:
                    continue
                seen.add(cite.quote)
                found.append({"text": cite.quote, "active": cite.quote == query.quote, "redacted": facet.redacted})
        return found

    def _source_label(self, document: str, page: int, query: WorkspaceQuery) -> str:
        if not document:
            return ""
        if document.startswith("clio:"):
            return "Clio"
        segment = _segment_at(self.segments, document, page)
        if not query.firm:
            if not segment:
                return "Record"
            relative = page - segment.page_start + 1
            return f"{segment.kind.value.replace('_', ' ').title()} · p. {relative}"
        name = Path(document).stem.split("__")[-1].replace("-", " ")
        return f"{name[:42]} · p. {page}"

    def _owned_segments(self, provider: str) -> list[Segment]:
        return [
            segment
            for segment in self.segments
            if segment.kind.value in _CLINICAL
            and _matches(provider, _blob(segment.facility, segment.authored_by, segment.source_file, segment.kind.value))
        ]

    def _provider_event(self, event: TimelineEvent, provider: str) -> bool:
        if event.sensitivity != Sensitivity.provider_visible:
            return False
        evidence = event.evidence[0] if event.evidence else None
        return _matches(provider, _blob(event.label, event.sensitivity_reason, evidence.document if evidence else "", evidence.quote if evidence else ""))

    def _value(self, key: str) -> str:
        for facet in self.facets:
            if facet.facet_key == key and facet.value and (self.query.firm or facet.sensitivity == Sensitivity.provider_visible):
                return facet.value
        return ""


def _segment_at(segments: list[Segment], document: str, page: int) -> Segment | None:
    for segment in segments:
        if segment.source_file == document and segment.page_start <= page <= segment.page_end:
            return segment
    return None


def _matches(provider: str, blob: str) -> bool:
    text = blob.lower()
    for key, _name, tokens in PROVIDERS:
        if key == provider:
            return any(token in text for token in tokens)
    return False


def _provider_name(blob: str) -> str:
    text = blob.lower()
    for _key, name, tokens in PROVIDERS:
        if any(token in text for token in tokens):
            return name
    return ""


def _blob(*parts: str) -> str:
    return " ".join(part for part in parts if part)


def _title(key: str) -> str:
    text = key.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    return text[:1].upper() + text[1:] if text else "Fact"


def _sensitive(label: str, reason: str) -> bool:
    text = f"{label} {reason}".lower()
    return any(bit in text for bit in ("ssn", "social", "license", "medicaid", "hiv", "hipaa", "policy", "employee"))


def _month_day(value: str | None) -> tuple[str, str]:
    if not value:
        return "?", "?"
    parts = value.split("-")
    month = _MONTHS[int(parts[1]) - 1] if len(parts) > 1 and parts[1].isdigit() else ""
    if len(parts) > 2 and parts[2][:2].isdigit():
        return month, str(int(parts[2][:2]))
    return month, "—" if month else "?"


def _pretty_date(value: str) -> str:
    if not value:
        return ""
    month, day = _month_day(value)
    year = value[:4]
    if day.isdigit():
        return f"{month.title()} {day}, {year}"
    if month:
        return f"{month.title()} {year}"
    return value


def _page_span(start: int, end: int) -> str:
    if start == end:
        return f"p. {start}"
    return f"pp. {start}–{end}"
