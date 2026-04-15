"""C2SIM protocol engine for S3M Phase 16 interoperability."""

from services.interop.c2sim.message_factory import C2SIMMessageFactory
from services.interop.c2sim.server_adapter import C2SIMServerAdapter

try:
    from services.interop.c2sim.c2sim_engine import C2SIMEngine
except ModuleNotFoundError:
    C2SIMEngine = None  # type: ignore[assignment]

__all__ = ["C2SIMEngine", "C2SIMMessageFactory", "C2SIMServerAdapter"]

