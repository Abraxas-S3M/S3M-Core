"""Deprecated: import from src.security.internal_channel.internal_secure_channel."""

from __future__ import annotations

import warnings

warnings.warn(
    "src.security.zkn.sealed_tunnel is deprecated; use "
    "src.security.internal_channel.internal_secure_channel",
    DeprecationWarning,
    stacklevel=2,
)

from src.security.internal_channel.internal_secure_channel import (  # noqa: E402
    InternalSecureChannel,
    TunnelEndpoint,
)

SealedTunnel = InternalSecureChannel

__all__ = ["SealedTunnel", "InternalSecureChannel", "TunnelEndpoint"]
