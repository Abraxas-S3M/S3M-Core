"""Deprecated: import from src.security.internal_channel.micro_segmentation."""

from __future__ import annotations

import warnings

warnings.warn(
    "src.security.zkn.micro_segmentation is deprecated; use "
    "src.security.internal_channel.micro_segmentation",
    DeprecationWarning,
    stacklevel=2,
)

from src.security.internal_channel.micro_segmentation import (  # noqa: E402
    AccessVerdict,
    MicroSegmentationPolicy,
    SegmentRule,
)

__all__ = ["MicroSegmentationPolicy", "SegmentRule", "AccessVerdict"]
