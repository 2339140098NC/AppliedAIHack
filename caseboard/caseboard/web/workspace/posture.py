"""Rank for the critical cards under the case summary."""

from caseboard.validate.critical import CRITICAL_PHRASES

CRITICAL_ORDER = list(CRITICAL_PHRASES)


def critical_rank(code: str) -> int:
    try:
        return CRITICAL_ORDER.index(code)
    except ValueError:
        return len(CRITICAL_ORDER)

