"""
S3M internal inter-process channel protection (Ring 2).

Outbound-only encrypted channels between layer processes, micro-segmentation,
and one-time-code authentication — internal S3M plumbing, not a vendor product.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.security.internal_channel.channel_manager import ChannelManager
from src.security.internal_channel.internal_secure_channel import (
    InternalSecureChannel,
    TunnelEndpoint,
)
from src.security.internal_channel.one_time_code_auth import OneTimeCodeAuthenticator, OneTimeCode
from src.security.internal_channel.micro_segmentation import (
    MicroSegmentationPolicy,
    SegmentRule,
    AccessVerdict,
)

_manager: Optional[ChannelManager] = None


def get_channel_manager() -> ChannelManager:
    """Return a process-wide channel manager singleton."""
    global _manager
    if _manager is None:
        _manager = ChannelManager()
    return _manager


def get_channel_status() -> Dict[str, Any]:
    """Lightweight status snapshot for GUI trust-fabric panels."""
    try:
        return get_channel_manager().get_status()
    except Exception:
        return {}


__all__ = [
    "InternalSecureChannel",
    "TunnelEndpoint",
    "OneTimeCodeAuthenticator",
    "OneTimeCode",
    "MicroSegmentationPolicy",
    "SegmentRule",
    "AccessVerdict",
    "ChannelManager",
    "get_channel_manager",
    "get_channel_status",
]
