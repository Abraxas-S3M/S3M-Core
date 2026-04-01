"""Hash-based deduplication for normalized integration records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from typing import Any, List, Set


class HashBasedDeduplicator:
    """Deduplicate records by stable content hash."""

    def __init__(self) -> None:
        self._seen_hashes: Set[str] = set()

    def _serialize(self, record: Any) -> str:
        if is_dataclass(record):
            payload = asdict(record)
        elif isinstance(record, dict):
            payload = record
        else:
            payload = {"value": str(record)}
        return json.dumps(payload, sort_keys=True, default=str)

    def add(self, record: Any) -> bool:
        digest = hashlib.sha256(self._serialize(record).encode("utf-8")).hexdigest()
        if digest in self._seen_hashes:
            return False
        self._seen_hashes.add(digest)
        return True

    def deduplicate(self, records: List[Any]) -> List[Any]:
        unique: List[Any] = []
        for record in records:
            if self.add(record):
                unique.append(record)
        return unique
