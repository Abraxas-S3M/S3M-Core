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
from services.interop.ogc import GeoJSONAdapter, WFSClient, WMSClient
from services.interop.oth import OTHGoldAdapter
from services.interop.registry import InteropRegistry
from services.interop.stix import STIXTAXIIBridge, TAXIIClient
from services.interop.symbology import SIDCGenerator, SymbologyMapper
from services.interop.tactical_mesh import TacticalMeshAdapter
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
    "WMSClient",
    "WFSClient",
    "GeoJSONAdapter",
    "MTFFormatter",
    "MTFTransport",
    "SIDCGenerator",
    "SymbologyMapper",
    "JREAPHandler",
    "JREAPBridge",
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
