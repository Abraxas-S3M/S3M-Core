"""MISP-Dashboard integration package.

Military/tactical context:
This wrapper standardizes threat-visualization ingestion for mission SOC
screens that need offline and low-latency indicator awareness.
"""

from .adapter import MispDashboardAdapter

__all__ = ["MispDashboardAdapter"]
