"""Canonical BackBlaze vault path helpers.

Military/tactical context:
Centralizing path builders prevents drift between nodes and reduces the risk
of accidentally syncing sensitive engine families to constrained platforms.
"""

from __future__ import annotations

import re
from typing import Iterable


class VaultPaths:
    """Path factory for dataset/model/adapter/checkpoint locations."""

    _SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")

    @classmethod
    def dataset_scenarios(cls, track: str) -> str:
        return f"datasets/{cls._segment(track, 'track')}/scenarios/"

    @classmethod
    def quantized_engine(cls, engine_id: str) -> str:
        return f"quantized/{cls._segment(engine_id, 'engine_id')}/"

    @classmethod
    def adapters(cls, engine_id: str, track: str | None = None) -> str:
        engine = cls._segment(engine_id, "engine_id")
        if track is None:
            return f"adapters/{engine}/"
        return f"adapters/{engine}/{cls._segment(track, 'track')}/"

    @classmethod
    def checkpoints(cls, node: str, track: str | None = None, engine_id: str | None = None) -> str:
        base = f"checkpoints/{cls._segment(node, 'node')}/"
        if track is not None:
            return f"{base}{cls._segment(track, 'track')}/"
        if engine_id is not None:
            return f"{base}{cls._segment(engine_id, 'engine_id')}/"
        return base

    @classmethod
    def eval_results(cls, node: str) -> str:
        return f"eval-results/{cls._segment(node, 'node')}/"

    @staticmethod
    def gui_snapshots() -> str:
        return "gui-snapshots/"

    @staticmethod
    def contains_blocked_token(path: str, blocked_tokens: Iterable[str]) -> bool:
        lowered_path = str(path or "").lower()
        for token in blocked_tokens:
            text = str(token or "").strip().lower()
            if text and text in lowered_path:
                return True
        return False

    @classmethod
    def _segment(cls, value: str, name: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{name} must be a non-empty string")
        if ".." in text or "/" in text or "\\" in text:
            raise ValueError(f"{name} contains invalid path characters")
        if cls._SEGMENT_RE.fullmatch(text) is None:
            raise ValueError(f"{name} contains unsupported characters")
        return text
