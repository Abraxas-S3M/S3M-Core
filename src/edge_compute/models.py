"""Data models for autonomous edge data generation pipelines."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class DataGenStrategy(str, Enum):
    """Strategy identifier for autonomous data generation outputs."""

    CONTRASTIVE = "contrastive"
    GENERATIVE_REPLAY = "generative_replay"
    ACTIVE_LEARNING = "active_learning"
    AUTO_ENTITY_LINKING = "auto_entity_linking"


@dataclass
class GeneratedDataset:
    """Metadata for a generated dataset artifact written to local disk."""

    strategy: DataGenStrategy
    record_count: int
    file_path: str
    file_size_bytes: int
    schema: Dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, DataGenStrategy):
            self.strategy = DataGenStrategy(str(self.strategy))
        if not isinstance(self.record_count, int) or self.record_count < 0:
            raise ValueError("record_count must be a non-negative integer")
        if not isinstance(self.file_path, str) or not self.file_path.strip():
            raise ValueError("file_path must be a non-empty string")
        if not isinstance(self.file_size_bytes, int) or self.file_size_bytes < 0:
            raise ValueError("file_size_bytes must be a non-negative integer")
        if not isinstance(self.schema, dict):
            raise ValueError("schema must be a dictionary")
