"""CoT protocol engine for S3M Phase 16 interoperability."""

from __future__ import annotations

from services.interop.cot.cot_bridge import CotBridge
from services.interop.cot.cot_event import CotEventFactory
from services.interop.cot.cot_transport import CotTransport

__all__ = ["CotEventFactory", "CotTransport", "CotBridge"]

