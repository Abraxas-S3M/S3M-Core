"""Incident response platform adapters for Layer 07 SOC integrations."""

from services.cyber.ir_platforms.base import IRPlatformAdapter
from services.cyber.ir_platforms.cortex_adapter import CortexAdapter
from services.cyber.ir_platforms.dfir_iris_adapter import DFIRIRISAdapter
from services.cyber.ir_platforms.ir_bridge import IRPlatformBridge
from services.cyber.ir_platforms.misp_adapter import MISPAdapter
from services.cyber.ir_platforms.thehive_adapter import TheHiveAdapter

__all__ = [
    "IRPlatformAdapter",
    "TheHiveAdapter",
    "CortexAdapter",
    "MISPAdapter",
    "DFIRIRISAdapter",
    "IRPlatformBridge",
]
