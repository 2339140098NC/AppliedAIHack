"""Assemble the workspace from the document store."""

import re
from calendar import month_abbr
from datetime import date
from pathlib import Path

from caseboard.domain.enums import DocType, GroupStatus, Sensitivity
from caseboard.domain.models import (
    CaseSummary,
    Charge,
    Communication,
    ComparisonGroup,
    Facet,
    Finding,
    Segment,
    SourceFile,
    ItemGlance,
    TimelineEvent,
)
from caseboard.extract.compare import merge_same
from caseboard.extract.stamp import extract_stamp
from caseboard.glance.text import glance_key
from caseboard.share.packet import load_share, share_status
from caseboard.store.documents import DocumentStore
from caseboard.validate.critical import CRITICAL_GLANCE
from caseboard.web.workspace.casefile import build_casefile
from caseboard.web.workspace.decisions import decision_actions
from caseboard.web.workspace.comms import comm_meta, comm_sub
from caseboard.web.workspace.extract_view import build_extract_detail
from caseboard.web.workspace.posture import critical_rank
from caseboard.web.workspace.status_bar import case_age
from caseboard.web.workspace.query import PROVIDERS, WorkspaceQuery

_MONTHS = [name.upper() for name in month_abbr if name]
_KIND = {"call": "Phone", "email": "Email", "note": "Note", "message": "Message"}
_CLINICAL = {"clinical_note", "imaging_report", "operative_report", "bill"}
_LOAD = (
    DocType.source,
    DocType.segment,
    DocType.facet,
    DocType.group,
    DocType.timeline_event,
    DocType.validation,
    DocType.communication,
    DocType.portrait,
    DocType.glance,
    DocType.charge,
    DocType.summary,
)
_SECTIONS = (
    ("sensitive", "Before sharing anything", "Things a provider must never see, or that must be fixed first."),
    ("conflict", "Facts that disagree", "Documents say different things. Decide which is right; don’t smooth it over."),
    ("incomplete", "Missing or blank", "Fields left empty, or papers the file mentions but doesn’t contain."),
)


class Workspace:
    """One render of the firm or provider workspace."""

    def __init__(self, store: DocumentStore, query: WorkspaceQuery) -> None:
        self.store = store
        self.query = query
        loaded = store.list_types(list(_LOAD))
        self.sources = [SourceFile.model_validate(row) for row in loaded[DocType.source]]
        self.segments = [Segment.model_validate(row) for row in loaded[DocType.segment]]
        self.facets = [Facet.model_validate(row) for row in loaded[DocType.facet]]
        self.groups = [ComparisonGroup.model_validate(row) for row in loaded[DocType.group]]
        self.events = [TimelineEvent.model_validate(row) for row in loaded[DocType.timeline_event]]
        self.findings = [Finding.model_validate(row) for row in loaded[DocType.validation]]
        self._comms = {
            item.clio_id: item
            for item in (Communication.model_validate(row) for row in loaded[DocType.communication])
        }
        self.has_portrait = bool(loaded[DocType.portrait])
        self.charges = [Charge.model_validate(row) for row in loaded[DocType.charge]]
        self.summary = _summary_line(loaded[DocType.summary])
        self.overview = _summary_overview(loaded[DocType.summary])
        self.summary_actions = _summary_actions(loaded[DocType.summary])
        self._glances = {
            item.id: item
            for item in (ItemGlance.model_validate(row) for row in loaded[DocType.glance])
        }
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
        critical = [item for item in open_items if str(item["code"]).startswith("critical_")]
        critical.sort(key=lambda item: critical_rank(item["code"]))
        attention = self._attention(query) if query.firm else []
        return {
            "query": query,
            "firm": query.firm,
            "provider_name": query.provider_name(),
            "providers": [(key, name) for key, name, _tokens in PROVIDERS],
            "plate": self._plate(len(critical) if query.firm else 0),
            "tabs": self._tabs(len(open_items)),
            "posture": self._posture(critical) if query.firm else "",
            "status": self._status(len(critical), attention, critical) if query.firm and query.tab == "timeline" else None,
            "critical": critical if query.firm else [],
            "urgent": attention[:6],
            "urgent_count": len(attention),
            "extract_detail": build_extract_detail(self.segments, self.facets, self.events, query),
            "years": self._years(query),
            "groups": self._groups(query),
            "facts": self._facts(query),
            "casefile": self._casefile(query),
            "findings": findings,
            "open_count": len(open_items),
            "finding_count": len(findings),
            "sections": _SECTIONS,
            "records": self._records(query),
            "viewer": self._viewer(query),
            "extractions": self._extractions(query),
            "portrait": query.firm and self.has_portrait,
            "share": self._share(query),
            "drawer_open": bool(query.drawer or query.document),
            "ev_compared": query.ev != "all",
        }

    def _with_viewer(self) -> WorkspaceQuery:
        return self.query

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
            cells.append({"k": "Critical", "v": str(open_count), "live": open_count > 0})
        else:
            owned = self._owned_segments(self.query.provider)
            cells = [
                {"k": "Client", "v": "Justin Sapini"},
                {"k": "Records", "v": f"{len(owned)} document{'s' if len(owned) != 1 else ''}"},
            ]
        return cells

    def _posture(self, _critical: list[dict]) -> str:
        return self.summary

    def _status(self, open_count: int, urgent: list[dict], critical: list[dict]) -> dict:
        accident = self._value("accident.datetime") or self._value("accident.date")
        pages = sum(item.page_count for item in self.sources)
        when = _pretty_date(accident)
        providers = self._provider_count()
        open_todos = sum(not item.resolved for item in self.findings)
        return {
            "summary": self.summary,
            "overview": self.overview,
            "actions": decision_actions(self.summary_actions, urgent, critical),
            "cards": [
                {"k": "Age of case", "v": case_age(accident, date.today()) or "—", "sub": f"Since {when}" if when else "", "href": ""},
                {"k": "Providers", "v": str(providers), "sub": "Treating" if providers else "", "href": self.query.url(tab="evidence", document="", page="", quote="", sel="")},
                {"k": "Critical", "v": str(open_count), "sub": f"Of {open_todos} to-dos" if open_todos else "", "href": self.query.url(tab="todo", document="", page="", quote="", sel="")},
                {"k": "PDFs", "v": str(len(self.sources)), "sub": f"{pages} pp." if pages else "", "href": ""},
            ],
        }

    def _provider_count(self) -> int:
        names = {
            segment.facility.strip().casefold()
            for segment in self.segments
            if segment.kind.value in _CLINICAL and segment.facility.strip()
        }
        return len(names)

    def _tabs(self, open_count: int) -> list[dict]:
        if self.query.firm:
            specs = [("timeline", "Overview", None), ("evidence", "Case", None), ("todo", "To-do", open_count or None)]
        else:
            specs = [("timeline", "Overview", None), ("records", "My records", None)]
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
        sub = event.time or ""
        record = None
        if document.startswith("clio:"):
            record = self._comms.get(document.removeprefix("clio:"))
            if record:
                sub = comm_sub(record) or sub
        form = _record_form(event, record, _segment_at(self.segments, document, page))
        if query.firm and who and not self._glances.get(glance_key(event)):
            kind = f"{kind} · {who}"
        glance = self._glances.get(glance_key(event))
        if glance:
            kind = glance.category
            label = glance.line
        else:
            label = event.label
        return {
            "id": event.id,
            "month": month,
            "day": day,
            "kind": kind,
            "form": form,
            "tone": _tone(kind),
            "urgent": bool(glance and glance.urgent),
            "label": label,
            "sub": sub,
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

    def _attention(self, query: WorkspaceQuery) -> list[dict]:
        """Urgent readings, newest first, for the summary."""
        rows = []
        for event in self.events:
            glance = self._glances.get(glance_key(event))
            if not glance or not glance.urgent:
                continue
            evidence = event.evidence[0] if event.evidence else None
            document = evidence.document if evidence else ""
            rows.append({
                "line": glance.line,
                "category": glance.category,
                "tone": _tone(glance.category),
                "date": event.date or "",
                "when": _pretty_date(event.date or "") or "No date",
                "href": query.url(
                    document=document,
                    page=evidence.page if evidence else 1,
                    quote=evidence.quote if evidence else "",
                    sel=event.id,
                ) if document else "",
            })
        rows.sort(key=lambda item: item["date"], reverse=True)
        return rows

    def _casefile(self, query: WorkspaceQuery) -> dict:
        if not query.firm:
            return {"expenses": [], "people": [], "disagreements": []}
        return build_casefile(
            self.facets,
            self.groups,
            self.segments,
            self.charges,
            query,
            lambda document, page: self._source_label(document, page, query),
        )

    def _groups(self, query: WorkspaceQuery) -> list[dict]:
        cards = []
        for group in self.groups:
            entries = [entry for entry in group.entries if query.firm or entry.sensitivity == Sensitivity.provider_visible]
            if not entries:
                continue
            merged = merge_same(group.facet_key, [(entry.value, entry.evidence) for entry in entries])
            rows = []
            for index, (value, cites) in enumerate(merged):
                rows.append({
                    "letter": _entry_letter(index) if len(merged) > 1 else "·",
                    "value": value or "Left blank",
                    "blank": not value,
                    "conflict": group.status == GroupStatus.conflict and len(merged) > 1,
                    "sources": [
                        {
                            "label": self._source_label(cite.document, cite.page, query),
                            "href": query.url(document=cite.document, page=cite.page, quote=cite.quote, sel=group.id, tab="evidence"),
                        }
                        for cite in cites
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
        visible = [
            facet
            for facet in self.facets
            if query.firm or facet.sensitivity == Sensitivity.provider_visible
        ]
        by_key: dict[str, list[Facet]] = {}
        for facet in visible:
            by_key.setdefault(facet.facet_key, []).append(facet)
        rows = []
        for key in sorted(by_key):
            facets = by_key[key]
            for value, cites in merge_same(key, [(facet.value, facet.evidence) for facet in facets]):
                if not cites:
                    continue
                shared = any(facet.sensitivity == Sensitivity.provider_visible for facet in facets)
                who = "Firm only"
                if shared:
                    who = _provider_name(_blob(key, cites[0].document)) or "Shared"
                rows.append({
                    "fact": _title(key),
                    "value": value or "Left blank",
                    "vis": who,
                    "sources": [
                        {
                            "label": self._source_label(cite.document, cite.page, query),
                            "href": query.url(
                                document=cite.document,
                                page=cite.page,
                                quote=cite.quote,
                                sel=facets[0].id,
                                tab="evidence",
                                ev="all",
                            ),
                        }
                        for cite in cites
                    ],
                })
        return rows

    def _findings(self) -> list[dict]:
        rows = []
        for finding in sorted(self.findings, key=lambda item: item.message):
            title, _, detail = finding.message.partition(". ")
            seen: set[tuple[str, int]] = set()
            sources = []
            for cite in finding.evidence:
                mark = (cite.document, cite.page)
                if not cite.document or mark in seen:
                    continue
                seen.add(mark)
                sources.append({
                    "label": self._source_label(cite.document, cite.page, self.query),
                    "name": _cite_name(cite.document),
                    "page": cite.page,
                    "href": self.query.url(document=cite.document, page=cite.page, quote=cite.quote, sel=finding.id, tab="todo"),
                })
            sources.sort(key=lambda item: (item["name"].lower(), item["page"]))
            rows.append({
                "id": finding.id,
                "code": finding.code,
                "severity": finding.severity.value,
                "title": title,
                "glance": CRITICAL_GLANCE.get(finding.code, title),
                "detail": detail or finding.code,
                "done": finding.resolved,
                "src": sources[0]["label"] if sources else "",
                "href": sources[0]["href"] if sources else "",
                "todo_href": self.query.url(tab="todo", sel=finding.id, document="", page="", quote=""),
                "sources": sources,
            })
        return rows

    def share_ids(self, query: WorkspaceQuery) -> list[str]:
        """Records this provider preview can include or hold back."""
        if query.firm:
            return []
        events = [event.id for event in self._visible_events(query)]
        facts = [facet.id for facet in self._provider_facets(query.provider)]
        documents = [segment.id for segment in self._owned_segments(query.provider)]
        return events + facts + documents

    def _share(self, query: WorkspaceQuery) -> dict | None:
        if query.firm:
            return None
        packet = load_share(self.store, query.provider)
        return share_status(packet, self.share_ids(query))

    def _provider_facets(self, provider: str) -> list[Facet]:
        found = []
        for facet in self.facets:
            if facet.sensitivity != Sensitivity.provider_visible or not facet.value:
                continue
            evidence = facet.evidence[0] if facet.evidence else None
            blob = _blob(facet.authored_by, facet.facet_key, evidence.document if evidence else "", facet.value)
            if _matches(provider, blob):
                found.append(facet)
        return found

    def _records(self, query: WorkspaceQuery) -> dict:
        facts = []
        for facet in self._provider_facets(query.provider):
            evidence = facet.evidence[0] if facet.evidence else None
            page = evidence.page if evidence else 1
            document = evidence.document if evidence else ""
            facts.append({
                "id": facet.id,
                "label": _title(facet.facet_key),
                "value": facet.value,
                "src": self._source_label(document, page, query),
                "href": query.url(document=document, page=page, quote=evidence.quote if evidence else "", tab="records") if document else "",
            })
        documents = []
        for segment in self._owned_segments(query.provider):
            documents.append({
                "id": segment.id,
                "label": segment.kind.value.replace("_", " ").title(),
                "pages": _page_span(segment.page_start, segment.page_end),
                "href": query.url(document=segment.source_file, page=segment.page_start, quote="", tab="records"),
            })
        return {"facts": facts, "documents": documents}

    def _extractions(self, query: WorkspaceQuery) -> list[dict]:
        current = extract_stamp()
        rows = []
        for source in sorted(self.sources, key=lambda item: item.filename):
            done = bool(source.extracted_at or source.clio_version_id)
            stale = bool(source.schema_id) and source.schema_id != current
            if not done:
                state, label = "waiting", "Not extracted"
            elif stale:
                state, label = "stale", "Schema changed"
            else:
                state, label = "done", "Extracted"
            rows.append({
                "filename": source.filename,
                "title": _title(Path(source.filename).stem.split("__")[-1]),
                "when": _extracted_when(source.extracted_at),
                "state": state,
                "label": label,
                "href": query.url(document=source.filename, page=1, quote="", drawer="1", panel=""),
                "extract_href": query.url(document=source.filename, page="", quote="", drawer="1", panel="extract"),
            })
        return rows

    def _viewer(self, query: WorkspaceQuery) -> dict:
        document = query.document
        if document.startswith("clio:") and query.firm:
            return self._communication_viewer(query, document)
        if document.startswith("clio:"):
            document = ""
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
        chips = _file_chips(self.segments, document, page, query) if query.firm else []
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
            "record": False,
            "body": "",
            "meta": [],
        }

    def _communication_viewer(self, query: WorkspaceQuery, document: str) -> dict:
        record = self._comms.get(document.removeprefix("clio:"))
        kind = _KIND.get(record.source.value, "Record") if record else "Record"
        when = _pretty_date(record.occurred_on or "") if record and record.occurred_on else ""
        if record and record.occurred_time:
            when = " · ".join(part for part in (when, record.occurred_time) if part)
        title = (record.subject.strip() if record and record.subject.strip() else kind) if record else "Record not found"
        meta = comm_meta(record) if record else []
        if record and record.body.strip():
            body = record.body
        elif record:
            body = "This record has no text."
        else:
            body = "This record is not in the store."
        return {
            "title": title,
            "sub": " · ".join(part for part in (kind, when) if part),
            "banner": "",
            "show_name": True,
            "document": document,
            "page": 1,
            "image": False,
            "chips": [],
            "page_label": "",
            "prev": "",
            "next": "",
            "seg_label": kind,
            "quotes": [],
            "footer": "",
            "record": True,
            "body": body,
            "meta": meta,
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
        evidence = event.evidence[0] if event.evidence else None
        document = evidence.document if evidence else ""
        if not _matches(provider, _blob(
            event.label,
            event.sensitivity_reason,
            document,
            evidence.quote if evidence else "",
            *_chart_bits(self.segments, document),
        )):
            return False
        if event.sensitivity == Sensitivity.provider_visible:
            return True
        return _own_chart(document)

    def _value(self, key: str) -> str:
        for facet in self.facets:
            if facet.facet_key == key and facet.value and (self.query.firm or facet.sensitivity == Sensitivity.provider_visible):
                return facet.value
        return ""


def _tone(category: str) -> str:
    text = category.split("·", 1)[0].strip().lower()
    known = {
        "accident": "accident",
        "treatment": "treatment",
        "imaging": "imaging",
        "surgery": "surgery",
        "bill": "bill",
        "pleading": "pleading",
        "discovery": "discovery",
        "expert": "expert",
        "insurance": "insurance",
        "client": "client",
        "court": "court",
        "phone": "client",
        "email": "client",
        "note": "client",
        "message": "client",
        "filing": "court",
        "correspondence": "client",
        "exam": "expert",
        "demand": "discovery",
        "call": "client",
    }
    return known.get(text, "treatment")


def _segment_at(segments: list[Segment], document: str, page: int) -> Segment | None:
    for segment in segments:
        if segment.source_file == document and segment.page_start <= page <= segment.page_end:
            return segment
    return None


def _cite_name(document: str) -> str:
    if document.startswith("clio:"):
        return "Clio"
    return Path(document).stem.split("__")[-1].replace("-", " ")[:42]


def _fold(value: str) -> str:
    """Hyphens and punctuation should not hide a provider's own file."""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _matches(provider: str, blob: str) -> bool:
    text = f" {_fold(blob)} "
    for key, _name, tokens in PROVIDERS:
        if key == provider:
            return any(f" {_fold(token)} " in text for token in tokens)
    return False


def _provider_name(blob: str) -> str:
    text = f" {_fold(blob)} "
    for _key, name, tokens in PROVIDERS:
        if any(f" {_fold(token)} " in text for token in tokens):
            return name
    return ""


def _chart_bits(segments: list[Segment], document: str) -> tuple[str, ...]:
    if not document:
        return ()
    return tuple(
        _blob(segment.facility, segment.authored_by, segment.source_file)
        for segment in segments
        if segment.source_file == document
    )


def _own_chart(document: str) -> bool:
    """An exam pulled from the provider's records, not a firm email or a pleading."""
    folded = _fold(document)
    return "medical record" in folded or "medical bill" in folded


def _blob(*parts: str) -> str:
    return " ".join(part for part in parts if part)


_FORM = {
    "email": "Email",
    "note": "Note",
    "call": "Phone",
    "phone": "Phone",
    "message": "Message",
    "filing": "Filing",
    "pleading": "Filing",
    "correspondence": "Letter",
    "exam": "Exam",
    "demand": "Demand",
    "accident": "Accident",
    "treatment": "Visit",
    "imaging": "Imaging",
    "imaging_report": "Imaging",
    "surgery": "Surgery",
    "operative_report": "Operative",
    "discovery": "Discovery",
    "bill": "Bill",
    "clinical_note": "Chart",
    "expert_report": "Expert",
    "incident_report": "Incident",
    "hipaa_authorization": "HIPAA",
    "photo_id": "ID",
}


def _record_form(event: TimelineEvent, record, segment: Segment | None) -> str:
    """The thing a lawyer scans: email, note, filing. The category stays separate."""
    if record is not None:
        return _FORM.get(record.source.value, "Record")
    if segment is not None:
        named = _FORM.get(segment.kind.value)
        if named:
            return named
    return _FORM.get(event.kind.value, "Record")


def _file_chips(segments: list[Segment], document: str, page: int, query: WorkspaceQuery) -> list[dict]:
    """Sections of one PDF, in page order. One section is highlighted."""
    if not document:
        return []
    rows = [item for item in segments if item.source_file == document]
    rows.sort(key=lambda item: (item.page_start, item.page_end, item.kind.value, item.id))
    if len(rows) < 2:
        return []
    matches = [item for item in rows if item.page_start <= page <= item.page_end]
    chosen = min(matches, key=lambda item: (item.page_end - item.page_start, item.page_start, item.id)) if matches else None
    return [
        {
            "label": item.kind.value.replace("_", " ").title(),
            "range": _page_span(item.page_start, item.page_end),
            "active": chosen is not None and item.id == chosen.id,
            "href": query.url(document=document, page=item.page_start, quote=""),
        }
        for item in rows
    ]


def _summary_line(rows: list[dict]) -> str:
    if not rows:
        return ""
    return CaseSummary.model_validate(rows[0]).line


def _summary_overview(rows: list[dict]) -> str:
    if not rows:
        return ""
    return CaseSummary.model_validate(rows[0]).overview


def _summary_actions(rows: list[dict]) -> list[str]:
    if not rows:
        return []
    return list(CaseSummary.model_validate(rows[0]).actions)


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


def _extracted_when(value: str) -> str:
    if not value:
        return ""
    return value.replace("T", " ").removesuffix("Z") + " UTC"


def _entry_letter(index: int) -> str:
    if index < 26:
        return chr(ord("A") + index)
    return str(index + 1)


def _page_span(start: int, end: int) -> str:
    if start == end:
        return f"p. {start}"
    return f"pp. {start}–{end}"
