"""Cross-provider entity resolution for correlated operational entities."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List


class CrossProviderEntityResolver:
    """Group records that likely describe the same tactical entity."""

    def __init__(self, key_fields: List[str]) -> None:
        self.key_fields = key_fields

    def _record_value(self, record: Any, field: str) -> str:
        if isinstance(record, dict):
            value = record.get(field)
        else:
            value = getattr(record, field, None)
        return str(value).strip().lower() if value is not None else ""

    def resolve(self, records: List[Any]) -> Dict[str, List[Any]]:
        groups: Dict[str, List[Any]] = defaultdict(list)
        for record in records:
            key_parts = [self._record_value(record, field) for field in self.key_fields]
            entity_key = "|".join(key_parts)
            groups[entity_key].append(record)
        return dict(groups)
