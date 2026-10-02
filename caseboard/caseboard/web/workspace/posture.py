"""One sentence for where the case stands."""

from caseboard.validate.critical import CRITICAL_PHRASES

CRITICAL_ORDER = list(CRITICAL_PHRASES)


def posture_sentence(
    *,
    name: str,
    index: str,
    prior: str,
    accident: str,
    open_codes: list[str],
) -> str:
    """Settled facts, then the open critical stories in demo order."""
    client = name or "Justin Sapini"
    current = index or "160000/2024"
    when = accident or "April 23, 2023"
    sentence = f"{client}. Index {current}."
    if prior:
        sentence += f" Earlier index {prior} is also in the file."
    sentence += f" Accident {when}."
    phrases = [CRITICAL_PHRASES[code] for code in open_codes if code in CRITICAL_PHRASES]
    if phrases:
        sentence += " Open: " + _and(phrases) + "."
    else:
        sentence += " No critical conflicts are open."
    return sentence


def critical_rank(code: str) -> int:
    try:
        return CRITICAL_ORDER.index(code)
    except ValueError:
        return len(CRITICAL_ORDER)


def _and(items: list[str]) -> str:
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]
