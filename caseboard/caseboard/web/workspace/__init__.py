"""View models for the case workspace."""

from caseboard.web.workspace.board import Workspace
from caseboard.web.workspace.query import parse_query

__all__ = ["Workspace", "parse_query"]
