"""
S3M Simulation-to-Reality Transfer Bridge
=========================================
Bridges simulated training and real deployment using domain randomization
and transfer-gap assessment to reduce tactical performance regressions.
"""

from src.simulation.sim2real.domain_randomizer import (
    DomainRandomizer,
    RandomizationConfig,
    RandomizedSample,
)
from src.simulation.sim2real.transfer_bridge import (
    GapAssessment,
    TransferBridge,
    TransferMetrics,
)

__all__ = [
    "DomainRandomizer",
    "RandomizationConfig",
    "RandomizedSample",
    "TransferBridge",
    "TransferMetrics",
    "GapAssessment",
]
