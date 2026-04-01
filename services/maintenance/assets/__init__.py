"""Asset and fleet management interfaces for Layer 11."""

from services.maintenance.assets.asset_registry import AssetRegistry
from services.maintenance.assets.erp_adapter import ERPAdapter
from services.maintenance.assets.fleet_manager import FleetManager

__all__ = ["AssetRegistry", "FleetManager", "ERPAdapter"]
