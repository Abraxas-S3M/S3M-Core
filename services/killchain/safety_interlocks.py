"""Hard safety interlocks for autonomous kill-chain execution.

Military context:
These non-bypassable constraints enforce lawful targeting behavior and prevent
unsafe engagement release even if upstream logic or operators misconfigure flow.
"""

from __future__ import annotations

from typing import List, Tuple

from services.killchain.models import EngagementRequest


class KillChainSafetyInterlocks:
    """Non-overridable engagement blockers for safety-critical operations."""

    def __init__(self):
        self._status = [
            {"id": 1, "name": "military_objective_required", "active": True},
            {"id": 2, "name": "collateral_unacceptable_block", "active": True},
            {"id": 3, "name": "civilian_target_block", "active": True},
            {"id": 4, "name": "minimum_confidence_block", "active": True},
            {"id": 5, "name": "audit_entry_required", "active": True},
            {"id": 6, "name": "roe_compliance_required", "active": True},
            {"id": 7, "name": "xai_required", "active": True},
        ]

    def validate_engagement(self, request: EngagementRequest) -> Tuple[bool, str]:
        """Apply 7 hard interlocks and return allow/block with reason."""
        assessment_text = (request.threat_assessment or "").upper()
        collateral_text = (request.collateral_estimate or "").upper()

        if '"IS_VALID_TARGET": FALSE' in assessment_text or "IS_MILITARY_OBJECTIVE=FALSE" in assessment_text:
            return False, "BLOCKED: target not confirmed as military objective"

        if "UNACCEPTABLE" in collateral_text:
            return False, "BLOCKED: unacceptable collateral damage"

        if "CIVILIAN" in assessment_text:
            return False, "BLOCKED: civilian target"

        if float(request.confidence) < 0.5:
            return False, "BLOCKED: insufficient classification confidence"

        if int(request.__dict__.get("audit_entries_count", 0)) < 1:
            return False, "BLOCKED: missing hash-chained audit entry"

        if not bool(request.roe_compliant):
            return False, "BLOCKED: ROE violation"

        if not str(request.xai_explanation or "").strip():
            return False, "BLOCKED: missing XAI explanation"

        return True, "ALLOWED"

    def get_interlock_status(self) -> List[dict]:
        """Return runtime status of all interlocks for assurance monitoring."""
        return list(self._status)
