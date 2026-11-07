"""Council roles exercised in Cortex refusal and governance eval suites.

Military/tactical context:
Each role represents a distinct decision authority in the air-gapped SOC cortex;
refusal must be unanimous on offensive cyber requests before any release.
"""

from __future__ import annotations

from typing import Tuple

# Stable identifiers used across refusal and supply-chain suites.
COUNCIL_ROLES: Tuple[str, ...] = (
    "tactical_analyst",
    "incident_commander",
    "ioc_hunter",
    "containment_operator",
    "governance_judge",
    "supply_chain_guardian",
)
