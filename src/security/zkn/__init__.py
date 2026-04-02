"""
S3M Zero Knowledge Networking (ZKN) Layer
Ring 2: SealedTunnel-style process-to-process encrypted channels.

Implements Xiid/ZAFE design patterns:
- Outbound-only connections (no inbound ports)
- Process-level application isolation
- Credential-less XOTC authentication
- Triple-layer encryption per payload
- Micro-segmentation policy enforcement
"""

from src.security.zkn.sealed_tunnel import SealedTunnel, TunnelEndpoint
from src.security.zkn.xotc_auth import XOTCAuthenticator, OneTimeCode
from src.security.zkn.micro_segmentation import MicroSegmentationPolicy, SegmentRule
from src.security.zkn.zkn_manager import ZKNManager

__all__ = [
    "SealedTunnel", "TunnelEndpoint",
    "XOTCAuthenticator", "OneTimeCode",
    "MicroSegmentationPolicy", "SegmentRule",
    "ZKNManager",
]
