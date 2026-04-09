"""Validation gates for model adaptation artifact promotion.

Military/tactical context:
This package provides a second quality-control layer before adapters are moved
into operational sync paths, reducing the risk of degraded outputs in mission
briefing and command-support workflows.
"""

from src.training.validation.grok_oracle import (
    GrokValidationOracle,
    Verdict,
    VerdictRequest,
)

__all__ = ["GrokValidationOracle", "Verdict", "VerdictRequest"]
