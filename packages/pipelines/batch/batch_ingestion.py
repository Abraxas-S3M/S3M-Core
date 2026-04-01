"""Batch ingestion runner for provider fetch and local persistence."""

from __future__ import annotations

from typing import Any, Dict, List

from connectors.local_storage import LocalStorage
from integration_sdk.registry.provider_registry import ProviderRegistry


class BatchIngestionRunner:
    """Execute one ingestion cycle for a registered provider."""

    def __init__(self, registry: ProviderRegistry, storage: LocalStorage) -> None:
        self.registry = registry
        self.storage = storage

    def run(self, provider_id: str, params: Dict[str, Any] = None) -> List[Any]:
        adapter = self.registry.get(provider_id)
        if adapter is None:
            raise ValueError(f"Provider not available: {provider_id}")

        records = adapter.fetch_and_normalize(params or {})
        for record in records:
            self.storage.store(provider_id=provider_id, collection="normalized", record=record)
        return records
