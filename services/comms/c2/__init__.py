"""C2 routing, intelligence extraction, and security for Layer 08."""

from services.comms.c2.comms_security import CommsSecurityManager
from services.comms.c2.intel_extractor import MessageIntelExtractor
from services.comms.c2.message_router import C2MessageRouter

__all__ = ["C2MessageRouter", "MessageIntelExtractor", "CommsSecurityManager"]
