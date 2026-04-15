"""
S3M Layer 10 (Expanded) — Interoperability & Simulation Standards
Full-depth DIS/C2SIM/MSDL/ORBAT interoperability for GCC coalition exercises.

Subsystems:
- DIS Engine: Full IEEE-1278.1 protocol with 12+ PDU types, coordinate transforms, dead reckoning
- C2SIM Engine: Complete C2SIM server/client with NATO MSG-201 CWIX compatibility
- MSDL: Military Scenario Definition Language parser/generator for exercise initialization
- ORBAT Manager: Order of Battle composition, symbology, and tactical mapping
- Coalition Dashboard: Multi-partner exercise tracking with DIS/C2SIM data feeds
- Verification: IVCT-compatible interoperability testing framework
- Edge Mesh: TacticalMesh adapter for resilient coalition edge networking

Architecture:
  Phase 10 (src/security/interop/) = API surface (DISAdapter, C2SIMAdapter, BMLAdapter)
  Phase 16 (services/interop/)     = Deep implementations that Phase 10 delegates to
  Phase 7 Simulation → DIS PDUs → Coalition partners
  Phase 14 Comms → TacticalMesh → Edge relay for exercise networks
"""

from services.interop.c2sim import C2SIMEngine, C2SIMMessageFactory, C2SIMServerAdapter
from services.interop.coalition_dashboard import CoalitionDashboardProvider
from services.interop.cot import CotBridge, CotEventFactory, CotTransport
from services.interop.dis import (
    DISCoordinateConverter,
    DISDeadReckoning,
    DISEngine,
    DISNetworkManager,
    DISPDUFactory,
)
from services.interop.exercise_manager import ExerciseManager
from services.interop.jreap import JREAPBridge, JREAPHandler
from services.interop.mtf import MTFFormatter, MTFTransport
from services.interop.mip import MIPDataModel, MIPGateway, MIPObjectMapper
from services.interop.models import (
    DISEntityID,
    DISEntityType,
    DISHeader,
    DISLinearVelocity,
    DISOrientation,
    DISPDUType,
    DISWorldCoordinate,
    ExerciseSession,
    ForceStructure,
    MSDLScenario,
    ORBATUnit,
)
from services.interop.msdl import MSDLGenerator, MSDLParser, ORBATManager
from services.interop.nffi import NFFIGateway, NFFIMessageBuilder
from services.interop.nvg import NVGBuilder, NVGOverlayExchange, NVGParser
from services.interop.oth import OTHGoldAdapter
from services.interop.registry import InteropRegistry
from services.interop.stix import STIXTAXIIBridge, TAXIIClient
from services.interop.symbology import SIDCGenerator, SymbologyMapper
from services.interop.tactical_mesh import TacticalMeshAdapter
from services.interop.uas4586 import UAS4586Interface, UAS4586MessageHandler
from services.interop.verification import InteropVerifier

__all__ = [
    "DISEngine",
    "DISPDUFactory",
    "DISCoordinateConverter",
    "DISDeadReckoning",
    "C2SIMEngine",
    "C2SIMMessageFactory",
    "C2SIMServerAdapter",
    "CotEventFactory",
    "CotTransport",
    "CotBridge",
    "MSDLParser",
    "MSDLGenerator",
    "NFFIMessageBuilder",
    "NFFIGateway",
    "NVGBuilder",
    "NVGParser",
    "NVGOverlayExchange",
    "MTFFormatter",
    "MTFTransport",
    "SIDCGenerator",
    "SymbologyMapper",
    "JREAPHandler",
    "JREAPBridge",
    "HLAFederateAdapter",
    "HLAStubRTI",
    "OTHGoldAdapter",
    "ORBATManager",
    "ORBATUnit",
    "ForceStructure",
    "CoalitionDashboardProvider",
    "ExerciseManager",
    "ExerciseSession",
    "InteropVerifier",
    "TacticalMeshAdapter",
    "InteropRegistry",
    "TAXIIClient",
    "STIXTAXIIBridge",
    "DISHeader",
    "DISEntityID",
    "DISWorldCoordinate",
    "DISOrientation",
    "DISLinearVelocity",
    "DISEntityType",
    "DISPDUType",
    "MSDLScenario",
    "DISNetworkManager",
]

_EXPORT_MAP = {
    "DISEngine": ("services.interop.dis", "DISEngine"),
    "DISPDUFactory": ("services.interop.dis", "DISPDUFactory"),
    "DISCoordinateConverter": ("services.interop.dis", "DISCoordinateConverter"),
    "DISDeadReckoning": ("services.interop.dis", "DISDeadReckoning"),
    "C2SIMEngine": ("services.interop.c2sim", "C2SIMEngine"),
    "C2SIMMessageFactory": ("services.interop.c2sim", "C2SIMMessageFactory"),
    "C2SIMServerAdapter": ("services.interop.c2sim", "C2SIMServerAdapter"),
    "CotEventFactory": ("services.interop.cot", "CotEventFactory"),
    "CotTransport": ("services.interop.cot", "CotTransport"),
    "CotBridge": ("services.interop.cot", "CotBridge"),
    "MSDLParser": ("services.interop.msdl", "MSDLParser"),
    "MSDLGenerator": ("services.interop.msdl", "MSDLGenerator"),
    "NFFIMessageBuilder": ("services.interop.nffi", "NFFIMessageBuilder"),
    "NFFIGateway": ("services.interop.nffi", "NFFIGateway"),
    "MTFFormatter": ("services.interop.mtf", "MTFFormatter"),
    "MTFTransport": ("services.interop.mtf", "MTFTransport"),
    "SIDCGenerator": ("services.interop.symbology", "SIDCGenerator"),
    "SymbologyMapper": ("services.interop.symbology", "SymbologyMapper"),
    "JREAPHandler": ("services.interop.jreap", "JREAPHandler"),
    "JREAPBridge": ("services.interop.jreap", "JREAPBridge"),
    "HLAFederateAdapter": ("services.interop.hla", "HLAFederateAdapter"),
    "HLAStubRTI": ("services.interop.hla", "HLAStubRTI"),
    "OTHGoldAdapter": ("services.interop.oth", "OTHGoldAdapter"),
    "ORBATManager": ("services.interop.msdl", "ORBATManager"),
    "ORBATUnit": ("services.interop.models", "ORBATUnit"),
    "ForceStructure": ("services.interop.models", "ForceStructure"),
    "CoalitionDashboardProvider": ("services.interop.coalition_dashboard", "CoalitionDashboardProvider"),
    "ExerciseManager": ("services.interop.exercise_manager", "ExerciseManager"),
    "ExerciseSession": ("services.interop.models", "ExerciseSession"),
    "InteropVerifier": ("services.interop.verification", "InteropVerifier"),
    "TacticalMeshAdapter": ("services.interop.tactical_mesh", "TacticalMeshAdapter"),
    "InteropRegistry": ("services.interop.registry", "InteropRegistry"),
    "TAXIIClient": ("services.interop.stix", "TAXIIClient"),
    "STIXTAXIIBridge": ("services.interop.stix", "STIXTAXIIBridge"),
    "DISHeader": ("services.interop.models", "DISHeader"),
    "DISEntityID": ("services.interop.models", "DISEntityID"),
    "DISWorldCoordinate": ("services.interop.models", "DISWorldCoordinate"),
    "DISOrientation": ("services.interop.models", "DISOrientation"),
    "DISLinearVelocity": ("services.interop.models", "DISLinearVelocity"),
    "DISEntityType": ("services.interop.models", "DISEntityType"),
    "DISPDUType": ("services.interop.models", "DISPDUType"),
    "MSDLScenario": ("services.interop.models", "MSDLScenario"),
    "DISNetworkManager": ("services.interop.dis", "DISNetworkManager"),
}


def __getattr__(name: str):
    if name not in _EXPORT_MAP:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORT_MAP[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
