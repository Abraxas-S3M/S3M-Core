"""Deprecated import path for internal channel modules (removed next release)."""

from __future__ import annotations

import warnings

warnings.warn(
    "src.security.zkn is deprecated; use src.security.internal_channel instead",
    DeprecationWarning,
    stacklevel=2,
)

from src.security.internal_channel import (  # noqa: E402
    AccessVerdict,
    ChannelManager,
    InternalSecureChannel,
    MicroSegmentationPolicy,
    OneTimeCode,
    OneTimeCodeAuthenticator,
    SegmentRule,
    TunnelEndpoint,
    get_channel_manager,
    get_channel_status,
)

# Historical names retained one release for downstream imports.
SealedTunnel = InternalSecureChannel
XOTCAuthenticator = OneTimeCodeAuthenticator
ZKNManager = ChannelManager

get_zkn_status = get_channel_status


def get_zkn_manager():
    warnings.warn(
        "get_zkn_manager is deprecated; use get_channel_manager",
        DeprecationWarning,
        stacklevel=2,
    )
    return get_channel_manager()


__all__ = [
    "SealedTunnel",
    "InternalSecureChannel",
    "TunnelEndpoint",
    "XOTCAuthenticator",
    "OneTimeCodeAuthenticator",
    "OneTimeCode",
    "MicroSegmentationPolicy",
    "SegmentRule",
    "AccessVerdict",
    "ZKNManager",
    "ChannelManager",
    "get_zkn_status",
    "get_channel_status",
    "get_zkn_manager",
    "get_channel_manager",
]
