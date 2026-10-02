"""Short actions under the case sentence, pointed at a page or a to-do."""

import re

_WORD = re.compile(r"[A-Za-z]{4,}")


def decision_actions(labels: list[str], urgent: list[dict], critical: list[dict]) -> list[dict]:
    """Up to two buttons. Stored labels win; otherwise the newest urgent lines."""
    chosen = [label.strip() for label in labels if label.strip()][:2]
    if chosen:
        return [_linked(label, urgent, critical) for label in chosen]
    return [
        {"label": _short(item["line"]), "href": item["href"], "drawer": bool(item["href"])}
        for item in urgent[:2]
        if item.get("line")
    ]


def _linked(label: str, urgent: list[dict], critical: list[dict]) -> dict:
    words = set(_WORD.findall(label.casefold()))
    urgent_hit = _best(words, urgent, "line")
    if urgent_hit is not None:
        return {"label": label, "href": urgent_hit["href"], "drawer": bool(urgent_hit["href"])}
    critical_hit = _best(words, critical, "glance")
    if critical_hit is not None:
        href = critical_hit["todo_href"]
        return {"label": label, "href": f"{href}#todo-{critical_hit['id']}", "drawer": False}
    return {"label": label, "href": "", "drawer": False}


def _best(words: set[str], rows: list[dict], field: str) -> dict | None:
    best = None
    score = 0
    for row in rows:
        overlap = len(words & set(_WORD.findall(str(row.get(field, "")).casefold())))
        if overlap > score:
            best = row
            score = overlap
    return best


def _short(line: str) -> str:
    return " ".join(line.split()[:6]).rstrip(".,;")
