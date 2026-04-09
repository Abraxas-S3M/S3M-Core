"""Streamlit-Cybersecurity-Dashboard integration package.

Military/tactical context:
This wrapper supports rapid SOC visual triage by standardizing dashboard data
flows for disconnected tactical operations centers.
"""

from .adapter import StreamlitCybersecurityDashboardAdapter

__all__ = ["StreamlitCybersecurityDashboardAdapter"]
