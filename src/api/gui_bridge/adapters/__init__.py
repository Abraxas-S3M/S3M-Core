"""Adapters that translate backend data into GUI workspace schemas.

This package reshapes core runtime/service outputs so tactical operator
workspaces can consume a stable API contract.
"""

from .decision_adapter import DecisionAdapter
from .risk_adapter import RiskAdapter

__all__ = ["DecisionAdapter", "RiskAdapter"]
