"""World Intelligence dual-source runtime control package.

Military/tactical context:
Provides sovereign gateway controls that keep command-intelligence routing
inside S3M-Core with controlled fallback and offline-safe degradation.
"""

from .models import WorldIntelligenceMode, WorldIntelligenceSource
from .routes import world_intelligence_router
from .runtime_manager import RuntimeManager
from .source_manager import SourceManager

__all__ = [
    "RuntimeManager",
    "SourceManager",
    "WorldIntelligenceMode",
    "WorldIntelligenceSource",
    "world_intelligence_router",
]
