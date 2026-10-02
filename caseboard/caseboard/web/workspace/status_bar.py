"""High-level cards for the top of the firm timeline."""

from datetime import date


def case_age(accident: str, today: date) -> str:
    """Whole years and months since the accident. An empty date stays blank."""
    parsed = _date(accident)
    if parsed is None or parsed > today:
        return ""
    months = (today.year - parsed.year) * 12 + today.month - parsed.month
    if today.day < parsed.day:
        months -= 1
    if months < 0:
        return ""
    years, rest = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} yr")
    if rest:
        parts.append(f"{rest} mo")
    return " ".join(parts) or "0 mo"


def _date(value: str) -> date | None:
    text = value.strip()
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        return None
    try:
        return date(int(text[:4]), int(text[5:7]), int(text[8:10]))
    except ValueError:
        return None
