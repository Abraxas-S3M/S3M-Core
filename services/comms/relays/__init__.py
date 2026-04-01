"""Relay adapters for S3M secure communications."""

from services.comms.relays.matrix_adapter import MatrixAdapter
from services.comms.relays.meshtastic_adapter import MeshtasticAdapter
from services.comms.relays.p2p_relay_adapter import P2PRelayAdapter
from services.comms.relays.relay_manager import RelayManager
from services.comms.relays.rocketchat_adapter import RocketChatAdapter
from services.comms.relays.simulated_relay import SimulatedRelay
from services.comms.relays.xmpp_adapter import XMPPAdapter

__all__ = [
    "SimulatedRelay",
    "MatrixAdapter",
    "MeshtasticAdapter",
    "XMPPAdapter",
    "RocketChatAdapter",
    "P2PRelayAdapter",
    "RelayManager",
]
