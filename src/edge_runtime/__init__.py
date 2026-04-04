"""
S3M Phase 21 - Austere Edge Runtime.
CPU-first, local-first, multi-bearer resilient runtime for denied environments.
UNCLASSIFIED - FOUO
"""

from src.edge_runtime.hardware_profiler import HardwareProfiler, NodeProfile, HardwareTier

# These components are loaded opportunistically because Module A is delivered
# independently. In austere deployments this keeps hardware profiling usable
# even before all runtime modules are staged on the node image.
try:
    from src.edge_runtime.degradation_controller import (
        DegradationController,
        ModePolicy,
        OperatingMode,
    )
except Exception:  # pragma: no cover - exercised when later modules are absent
    DegradationController = None  # type: ignore[assignment]
    ModePolicy = None  # type: ignore[assignment]
    OperatingMode = None  # type: ignore[assignment]

try:
    from src.edge_runtime.model_planner import (
        DEFAULT_VARIANTS,
        ExecutionDecision,
        ExecutionPlan,
        ModelExecutionPlanner,
        ModelVariant,
        Precision,
    )
except Exception:  # pragma: no cover - exercised when later modules are absent
    DEFAULT_VARIANTS = None  # type: ignore[assignment]
    ExecutionDecision = None  # type: ignore[assignment]
    ExecutionPlan = None  # type: ignore[assignment]
    ModelExecutionPlanner = None  # type: ignore[assignment]
    ModelVariant = None  # type: ignore[assignment]
    Precision = None  # type: ignore[assignment]

try:
    from src.edge_runtime.model_manifest import ManifestVariant, ModelManifest
except Exception:  # pragma: no cover - exercised when later modules are absent
    ManifestVariant = None  # type: ignore[assignment]
    ModelManifest = None  # type: ignore[assignment]

try:
    from src.edge_runtime.bearer_broker import (
        BearerBroker,
        DeliveryMode,
        LinkMetrics,
        LinkState,
        LinkType,
        MessageClass,
        RoutingDecision,
    )
except Exception:  # pragma: no cover - exercised when later modules are absent
    BearerBroker = None  # type: ignore[assignment]
    DeliveryMode = None  # type: ignore[assignment]
    LinkMetrics = None  # type: ignore[assignment]
    LinkType = None  # type: ignore[assignment]
    LinkState = None  # type: ignore[assignment]
    MessageClass = None  # type: ignore[assignment]
    RoutingDecision = None  # type: ignore[assignment]

try:
    from src.edge_runtime.durable_queue import (
        DurableQueue,
        QueueItem,
        QueueItemState,
        SyncReconciler,
    )
except Exception:  # pragma: no cover - exercised when later modules are absent
    DurableQueue = None  # type: ignore[assignment]
    QueueItem = None  # type: ignore[assignment]
    QueueItemState = None  # type: ignore[assignment]
    SyncReconciler = None  # type: ignore[assignment]

try:
    from src.edge_runtime.health_surface import OperatorHealthSurface
except Exception:  # pragma: no cover - exercised when later modules are absent
    OperatorHealthSurface = None  # type: ignore[assignment]

try:
    from src.edge_runtime.cpu_orchestrator import CPUOrchestrator
except Exception:  # pragma: no cover - exercised when later modules are absent
    CPUOrchestrator = None  # type: ignore[assignment]

try:
    from src.edge_runtime.bootstrap import AustereEdgeRuntime
except Exception:  # pragma: no cover - exercised when later modules are absent
    AustereEdgeRuntime = None  # type: ignore[assignment]

__all__ = [
    "HardwareProfiler", "NodeProfile", "HardwareTier",
    "DegradationController", "ModePolicy", "OperatingMode",
    "DEFAULT_VARIANTS", "ExecutionDecision", "ExecutionPlan",
    "ModelExecutionPlanner", "ModelVariant", "Precision",
    "ManifestVariant", "ModelManifest",
    "BearerBroker", "DeliveryMode", "LinkMetrics", "LinkType", "LinkState", "MessageClass", "RoutingDecision",
    "DurableQueue", "QueueItem", "QueueItemState", "SyncReconciler",
    "OperatorHealthSurface",
    "CPUOrchestrator",
    "AustereEdgeRuntime",
]
