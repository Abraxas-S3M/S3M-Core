"""World Monitor dashboard integration package.

Military/tactical context:
This wrapper provides standardized access to geopolitical dashboard signals
used to support command-level risk awareness in disconnected environments.
"""

from .adapter import WorldMonitorAdapter

__all__ = ["WorldMonitorAdapter"]
