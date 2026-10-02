"""Errors the dashboard can show without a stack trace."""


class CaseboardError(Exception):
    """A known failure in extraction, sync, or storage."""
