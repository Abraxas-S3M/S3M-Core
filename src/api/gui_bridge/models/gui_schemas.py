"""Shared GUI bridge schemas.

These models normalize payload shape for tactical GUI panels so each
workspace can consume a consistent envelope regardless of backend source.
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel


class GUIEnvelope(BaseModel):
    """Common envelope used by GUI workspace adapters."""

    type: str
    payload: Dict[str, Any]
    timestamp: str


class WorkspaceLink(BaseModel):
    """Pointer that allows the GUI to deep-link into a mission workspace."""

    workspace: str
    resourceId: Optional[str] = None


__all__ = ["GUIEnvelope", "WorkspaceLink"]
