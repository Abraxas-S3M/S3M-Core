"""Supply-Chain-Management-Dashboard integration package.

Military/tactical context:
This wrapper helps logistics command elements ingest inventory and supplier
dashboard views under disconnected operational constraints.
"""

from .adapter import SupplyChainManagementDashboardAdapter

__all__ = ["SupplyChainManagementDashboardAdapter"]
