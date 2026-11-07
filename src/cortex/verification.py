"""Verification and rollback for completed Cortex cases."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from s3m_core.defense.audit.merkle_log import MerkleAuditLog


@dataclass(frozen=True, slots=True)
class VerificationResult:
    audit_chain_ok: bool
    rollback_applied: bool
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "audit_chain_ok": bool(self.audit_chain_ok),
            "rollback_applied": bool(self.rollback_applied),
            "notes": self.notes,
        }


def verify_and_rollback(*, audit_log_path: str, apply_rollback: bool = False) -> VerificationResult:
    """
    Verify Merkle audit integrity; optionally mark rollback for failed broker effects.

    Tactical context: rollback is bookkeeping in offline tests — production applies
    broker undo via XiiD compensating transactions.
    """
    report = MerkleAuditLog(audit_log_path).verify_integrity()
    if not report.chain_intact:
        return VerificationResult(
            audit_chain_ok=False,
            rollback_applied=bool(apply_rollback),
            notes=f"broken at entry {report.first_broken_entry}",
        )
    return VerificationResult(
        audit_chain_ok=True,
        rollback_applied=bool(apply_rollback),
        notes="chain intact",
    )
