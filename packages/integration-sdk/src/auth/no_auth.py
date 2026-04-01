"""No-auth strategy for public or open-standard providers."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

from base.auth_strategy import AuthStrategy


class NoAuth(AuthStrategy):
    """Pass-through auth strategy for unauthenticated endpoints."""

    def apply(
        self,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        return dict(headers or {}), dict(params or {})
