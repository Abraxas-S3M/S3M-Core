"""Authentication strategy interfaces for provider adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple


class AuthStrategy(ABC):
    """Applies authentication material to outbound provider requests."""

    @abstractmethod
    def apply(
        self,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Return updated (headers, params) for authenticated requests."""

    def validate(self) -> bool:
        """Return whether current auth configuration is operational."""
        return True
