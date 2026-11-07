"""Deprecated: import from src.security.internal_channel.channel_manager."""

from __future__ import annotations

import warnings

warnings.warn(
    "src.security.zkn.zkn_manager is deprecated; use "
    "src.security.internal_channel.channel_manager",
    DeprecationWarning,
    stacklevel=2,
)

from src.security.internal_channel.channel_manager import ChannelManager  # noqa: E402

ZKNManager = ChannelManager

__all__ = ["ZKNManager", "ChannelManager"]
