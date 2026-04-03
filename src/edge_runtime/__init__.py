"""
S3M Phase 21 — Austere Edge Runtime
CPU-first, local-first, multi-bearer resilient runtime for denied environments.
"""

from src.edge_runtime.hardware_profiler import HardwareProfiler, NodeProfile, HardwareTier

# These components are loaded opportunistically because Module A is delivered
# independently. In austere deployments this keeps hardware profiling usable
# even before all runtime modules are staged on the node image.
try:
    from src.edge_runtime.degradation_controller import DegradationController, OperatingMode
except Exception:  # pragma: no cover - exercised when later modules are absent
    DegradationController = None  # type: ignore[assignment]
    OperatingMode = None  # type: ignore[assignment]

try:
    from src.edge_runtime.model_planner import ModelExecutionPlanner
except Exception:  # pragma: no cover - exercised when later modules are absent
    ModelExecutionPlanner = None  # type: ignore[assignment]

try:
    from src.edge_runtime.bearer_broker import BearerBroker, LinkType, LinkState, MessageClass
except Exception:  # pragma: no cover - exercised when later modules are absent
    BearerBroker = None  # type: ignore[assignment]
    LinkType = None  # type: ignore[assignment]
    LinkState = None  # type: ignore[assignment]
    MessageClass = None  # type: ignore[assignment]

try:
    from src.edge_runtime.durable_queue import DurableQueue, SyncReconciler
except Exception:  # pragma: no cover - exercised when later modules are absent
    DurableQueue = None  # type: ignore[assignment]
    SyncReconciler = None  # type: ignore[assignment]

try:
    from src.edge_runtime.health_surface import OperatorHealthSurface
except Exception:  # pragma: no cover - exercised when later modules are absent
    OperatorHealthSurface = None  # type: ignore[assignment]

__all__ = [
    "HardwareProfiler", "NodeProfile", "HardwareTier",
    "DegradationController", "OperatingMode",
    "ModelExecutionPlanner",
    "BearerBroker", "LinkType", "LinkState", "MessageClass",
    "DurableQueue", "SyncReconciler",
    "OperatorHealthSurface",
]
