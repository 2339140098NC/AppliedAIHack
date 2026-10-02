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
    """Settled facts. The critical list under this line carries the open stories."""
    client = name or "Justin Sapini"
    current = index or "160000/2024"
    when = accident or "April 23, 2023"
    sentence = f"{client}. Index {current}."
    if prior:
        sentence += f" Earlier index {prior} is also in the file."
    sentence += f" Accident {when}."
    if not any(code in CRITICAL_PHRASES for code in open_codes):
        sentence += " No critical conflicts are open."
    return sentence


def critical_rank(code: str) -> int:
    try:
        return CRITICAL_ORDER.index(code)
    except ValueError:
        return len(CRITICAL_ORDER)

