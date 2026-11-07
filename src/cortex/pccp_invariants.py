"""PCCP invariant checks for Cortex case evidence packs.

Military/tactical context: mutations must stay inside commander envelopes with
broker-only execution and a fail-closed policy gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True, slots=True)
class PCCPInvariants:
    broker_only_mutations: bool
    gate_fail_closed: bool
    trace_case_linked: bool
    audit_chain_intact: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "broker_only_mutations": bool(self.broker_only_mutations),
            "gate_fail_closed": bool(self.gate_fail_closed),
            "trace_case_linked": bool(self.trace_case_linked),
            "audit_chain_intact": bool(self.audit_chain_intact),
        }

    @property
    def all_satisfied(self) -> bool:
        return all(
            (
                self.broker_only_mutations,
                self.gate_fail_closed,
                self.trace_case_linked,
                self.audit_chain_intact,
            )
        )


def evaluate_pccp(
    *,
    broker_used: bool,
    direct_change_blocked: bool,
    gate_fail_closed: bool,
    trace_matches_case: bool,
    audit_chain_intact: bool,
) -> PCCPInvariants:
    return PCCPInvariants(
        broker_only_mutations=bool(broker_used or direct_change_blocked),
        gate_fail_closed=bool(gate_fail_closed),
        trace_case_linked=bool(trace_matches_case),
        audit_chain_intact=bool(audit_chain_intact),
    )
