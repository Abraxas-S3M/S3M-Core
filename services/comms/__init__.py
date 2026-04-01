"""
S3M Layer 08 — Secure Communications
Encrypted field-to-command messaging with Arabic NLP intelligence extraction.

Subsystems:
- Relay Manager: Orchestrates multiple encrypted messaging backends with priority fallback
- Platform Adapters: Matrix/Synapse, Meshtastic mesh, XMPP/ejabberd, Rocket.Chat, P2P relays
- Arabic NLP: Message summarization (AraBERT → mT5 → ALLaM → keyword fallback chain)
- C2 Routing: Priority-based military message routing with NLP enrichment
- Intel Extraction: Entities, intent, urgency scoring from message traffic
- Comms Security: Encryption, key management, classification enforcement

Data Flow:
  Field units → Encrypted relay (any backend) → S3M message bus → Arabic/English NLP
  → Summarized intel → Dashboard (Layer 06) + Threat Detection (Layer 02) + SOC (Layer 07)
  Command orders → NL parser → Autonomy (Layer 03) swarm commands
"""

from services.comms.c2 import C2MessageRouter, CommsSecurityManager, MessageIntelExtractor
from services.comms.comms_manager import CommsManager
from services.comms.models import (
    Channel,
    ChannelType,
    CommsNode,
    Message,
    MessagePriority,
    MessageStatus,
    MessageSummary,
    MessageType,
    NodeType,
    RelayBackend,
    RelayStatus,
)
from services.comms.nlp import ArabicNLPEngine
from services.comms.node_manager import CommsNodeManager
from services.comms.relays import (
    MatrixAdapter,
    MeshtasticAdapter,
    P2PRelayAdapter,
    RelayManager,
    RocketChatAdapter,
    SimulatedRelay,
    XMPPAdapter,
)

__all__ = [
    "CommsManager",
    "Message",
    "MessagePriority",
    "MessageType",
    "MessageStatus",
    "Channel",
    "ChannelType",
    "RelayBackend",
    "RelayStatus",
    "CommsNode",
    "NodeType",
    "MessageSummary",
    "ArabicNLPEngine",
    "MatrixAdapter",
    "MeshtasticAdapter",
    "XMPPAdapter",
    "RocketChatAdapter",
    "P2PRelayAdapter",
    "SimulatedRelay",
    "RelayManager",
    "C2MessageRouter",
    "MessageIntelExtractor",
    "CommsSecurityManager",
    "CommsNodeManager",
]
