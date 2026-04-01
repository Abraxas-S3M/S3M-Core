"""File-based storage connector for air-gapped provider data exchange."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class LocalStorage:
    """Store/query JSON records under mission-local integration storage."""

    def __init__(self, root_dir: str = "data/integrations") -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _to_serializable(self, record: Any) -> Dict[str, Any]:
        if is_dataclass(record):
            payload = asdict(record)
        elif isinstance(record, dict):
            payload = dict(record)
        else:
            payload = {"value": str(record)}
        return payload

    def _collection_path(self, provider_id: str, collection: str) -> Path:
        date_str = datetime.now(timezone.utc).date().isoformat()
        path = self.root_dir / provider_id / date_str
        path.mkdir(parents=True, exist_ok=True)
        return path / f"{collection}.jsonl"

    def store(self, collection: str, record: Any, provider_id: str = "default") -> Path:
        destination = self._collection_path(provider_id=provider_id, collection=collection)
        payload = self._to_serializable(record)
        with destination.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=str) + "\n")
        return destination

    def query(self, collection: str, filters: Dict[str, Any], provider_id: str = "default") -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        provider_dir = self.root_dir / provider_id
        if not provider_dir.exists():
            return results

        for jsonl_file in sorted(provider_dir.glob(f"*/{collection}.jsonl")):
            with jsonl_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if all(row.get(key) == value for key, value in filters.items()):
                        results.append(row)
        return results

    def count(self, collection: str, provider_id: str = "default") -> int:
        total = 0
        provider_dir = self.root_dir / provider_id
        if not provider_dir.exists():
            return 0
        for jsonl_file in provider_dir.glob(f"*/{collection}.jsonl"):
            with jsonl_file.open("r", encoding="utf-8") as handle:
                total += sum(1 for line in handle if line.strip())
        return total
