"""Decide when two extracted strings are the same fact."""

import re
from datetime import datetime

from caseboard.domain.models import Evidence

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%m/%d/%Y",
    "%m/%d/%Y %H:%M",
    "%m/%d/%y",
    "%m-%d-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
)
_NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "esq"}
_ADDRESS_DROP = {
    "ny",
    "n",
    "y",
    "new",
    "york",
    "county",
    "of",
    "state",
    "and",
    "the",
    "apt",
    "apartment",
    "unit",
    "suite",
    "ste",
    "texas",
    "tx",
    "rockland",
}


def compare_value(key: str, value: str | None) -> str:
    """Fold case, clock time, initials, and punctuation that do not change the fact."""
    if value is None or not value.strip():
        return ""
    raw = value.strip()
    parts = re.split(r"[._]", key.lower())
    if "name" in parts:
        return _name_key(raw)
    if any(bit in parts for bit in ("date", "datetime", "dob")):
        return calendar_day(raw) or _text_key(raw)
    if "index" in parts or "index_number" in key.lower():
        return re.sub(r"[^a-z0-9]", "", raw.lower())
    if "address" in parts:
        return _address_key(raw)
    return calendar_day(raw) or _text_key(raw)


def calendar_day(value: str | None) -> str:
    """Return YYYY-MM-DD when the whole string is a date, ignoring the clock."""
    if value is None or not value.strip():
        return ""
    text = value.strip().rstrip("Zz")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def merge_same(
    key: str,
    items: list[tuple[str | None, list[Evidence]]],
) -> list[tuple[str, list[Evidence]]]:
    """One row per distinct fact, with every citation that stated it."""
    order: list[str] = []
    buckets: dict[str, list[tuple[str | None, list[Evidence]]]] = {}
    for value, evidence in items:
        token = compare_value(key, value)
        if token not in buckets:
            order.append(token)
            buckets[token] = []
        buckets[token].append((value, evidence))
    rows = []
    for token in order:
        group = buckets[token]
        counts: dict[str, int] = {}
        for value, _evidence in group:
            if value and value.strip():
                counts[value.strip()] = counts.get(value.strip(), 0) + 1
        display = max(counts, key=lambda item: (counts[item], len(item))) if counts else ""
        seen: set[tuple[str, int]] = set()
        cites: list[Evidence] = []
        for _value, evidence in group:
            for cite in evidence:
                mark = (cite.document, cite.page)
                if not cite.document or mark in seen:
                    continue
                seen.add(mark)
                cites.append(cite)
        cites.sort(key=lambda cite: (cite.document, cite.page))
        rows.append((display, cites))
    return rows


def _name_key(value: str) -> str:
    tokens = re.sub(r"[^a-z]+", " ", value.lower()).split()
    kept = [token for token in tokens if len(token) > 1 and token not in _NAME_SUFFIXES]
    return " ".join(sorted(kept))


def _address_key(value: str) -> str:
    tokens = re.sub(r"[^a-z0-9]+", " ", value.lower()).split()
    kept = [token for token in tokens if token not in _ADDRESS_DROP and not re.fullmatch(r"\d{5}", token)]
    return " ".join(kept[:4])


def _text_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
