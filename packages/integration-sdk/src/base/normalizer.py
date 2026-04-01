"""Normalizer contract for transforming provider payloads into S3M schemas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseNormalizer(ABC):
    """Converts provider-specific payloads into normalized S3M records."""

    @abstractmethod
    def normalize(self, raw_data: Dict[str, Any]) -> List[Any]:
        """Map provider payloads into normalized schema objects."""
