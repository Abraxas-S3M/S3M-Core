"""Deprecated: import from src.security.internal_channel.one_time_code_auth."""

from __future__ import annotations

import warnings

warnings.warn(
    "src.security.zkn.xotc_auth is deprecated; use "
    "src.security.internal_channel.one_time_code_auth",
    DeprecationWarning,
    stacklevel=2,
)

from src.security.internal_channel.one_time_code_auth import (  # noqa: E402
    OneTimeCode,
    OneTimeCodeAuthenticator,
)

XOTCAuthenticator = OneTimeCodeAuthenticator

__all__ = ["XOTCAuthenticator", "OneTimeCodeAuthenticator", "OneTimeCode"]
