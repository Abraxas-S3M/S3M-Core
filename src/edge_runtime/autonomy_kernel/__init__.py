"""
S3M Edge Autonomy Kernel — Offline-First Decision Making
=========================================================
Provides autonomous operation when connectivity is degraded or absent.
The kernel maintains local decision authority, priority-based compute
allocation, and bandwidth-aware model switching.
"""

from src.edge_runtime.autonomy_kernel.bandwidth_router import (
    BandwidthRouter,
    BandwidthState,
    ModelSwitchDecision,
)
from src.edge_runtime.autonomy_kernel.offline_brain import (
    OfflineBrain,
    OfflineConfig,
    OfflineDecision,
)
from src.edge_runtime.autonomy_kernel.priority_allocator import (
    AllocationResult,
    ComputeTask,
    PriorityAllocator,
)

__all__ = [
    "OfflineBrain",
    "OfflineDecision",
    "OfflineConfig",
    "BandwidthRouter",
    "BandwidthState",
    "ModelSwitchDecision",
    "PriorityAllocator",
    "ComputeTask",
    "AllocationResult",
]
