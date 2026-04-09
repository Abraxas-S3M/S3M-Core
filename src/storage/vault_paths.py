"""Canonical BackBlaze B2 bucket layout for dual-precision S3M vault.

Military/tactical context:
This path catalog separates training-grade FP16 "source-of-truth" artifacts
from CPU-serving Q4 derivatives, preventing accidental downgrade of critical
model states during mission rehearsal and field serving workflows.
"""

from __future__ import annotations

import re
from typing import Iterable


class VaultPaths:
    """Canonical BackBlaze B2 bucket layout for dual-precision S3M vault.

    ARCHITECTURE RULE:
    - FP16 (full-precision) = source of truth for training
    - Q4 GGUF (quantized) = derived product for inference/serving
    - Training always reads FP16. Serving always reads Q4.
    - After each training cycle: FP16 adapter merges into FP16 base,
      then FP16 merged model gets quantized to produce new Q4.
    """

    _SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")

    # -- FP16 Master Weights (source of truth) ---------------------------------
    FP16_BASE = "models/fp16/{engine_id}/"

    # -- Q4 GGUF Serving Weights (derived from FP16) -----------------------------
    Q4_SERVING = "models/q4-gguf/{engine_id}/"

    # -- FP16 Adapters (training output) -----------------------------------------
    FP16_ADAPTERS = "adapters/fp16/{engine_id}/{track}/"

    # -- FP16 Merged Models (post-merge, pre-quantize) ---------------------------
    FP16_MERGED = "models/fp16-merged/{engine_id}/{track}/"

    # -- Training Data ------------------------------------------------------------
    DATASETS = "datasets/{track}/scenarios/"
    DATASETS_SHARED = "datasets/shared/scenarios/"

    # -- Checkpoints --------------------------------------------------------------
    CHECKPOINTS_HETZNER = "checkpoints/hetzner/{track}/"
    CHECKPOINTS_RUNPOD = "checkpoints/runpod/{engine_id}/"

    # -- Evaluation Results -------------------------------------------------------
    EVAL_RESULTS = "eval-results/{engine_id}/{track}/"

    # -- Grok Validation Oracle ---------------------------------------------------
    GROK_PENDING = "grok-verdicts/pending/"
    GROK_APPROVED = "grok-verdicts/approved/"
    GROK_REJECTED = "grok-verdicts/rejected/"

    # -- GUI Snapshots ------------------------------------------------------------
    GUI_SNAPSHOTS = "gui-snapshots/"

    # -- Access Control Rules -----------------------------------------------------
    HETZNER_PULL_PATHS = [
        Q4_SERVING,
        FP16_BASE,
        FP16_ADAPTERS,
        DATASETS,
        DATASETS_SHARED,
    ]

    RUNPOD_PULL_PATHS = [
        FP16_BASE,
        DATASETS,
        DATASETS_SHARED,
        FP16_ADAPTERS,
    ]

    ENGINES_BLOCKED_FROM_PULL = ["grok-300b", "grok1", "grok"]
    ENGINES_TRAINABLE_GPU = ["phi3-medium", "mistral-7b", "allam-7b"]
    ENGINES_SERVABLE_CPU = ["phi3-medium", "mistral-7b", "allam-7b"]

    @classmethod
    def fp16_base(cls, engine_id: str) -> str:
        return cls.FP16_BASE.format(engine_id=cls._segment(engine_id, "engine_id"))

    @classmethod
    def q4_serving(cls, engine_id: str) -> str:
        return cls.Q4_SERVING.format(engine_id=cls._segment(engine_id, "engine_id"))

    @classmethod
    def fp16_adapter(cls, engine_id: str, track: str) -> str:
        return cls.FP16_ADAPTERS.format(
            engine_id=cls._segment(engine_id, "engine_id"),
            track=cls._segment(track, "track"),
        )

    @classmethod
    def fp16_merged(cls, engine_id: str, track: str) -> str:
        return cls.FP16_MERGED.format(
            engine_id=cls._segment(engine_id, "engine_id"),
            track=cls._segment(track, "track"),
        )

    @classmethod
    def dataset_scenarios(cls, track: str) -> str:
        return cls.DATASETS.format(track=cls._segment(track, "track"))

    @classmethod
    def is_blocked_engine(cls, engine_id: str) -> bool:
        text = str(engine_id or "").lower()
        return any(blocked in text for blocked in cls.ENGINES_BLOCKED_FROM_PULL)

    # ---------------------------------------------------------------------
    # Compatibility aliases for existing scripts/daemons.
    # ---------------------------------------------------------------------
    @classmethod
    def quantized_engine(cls, engine_id: str) -> str:
        """Legacy alias retained for sync daemon compatibility."""
        return cls.q4_serving(engine_id)

    @classmethod
    def adapters(cls, engine_id: str, track: str | None = None) -> str:
        """Legacy alias retained for sync daemon compatibility."""
        if track is None:
            return f"adapters/fp16/{cls._segment(engine_id, 'engine_id')}/"
        return cls.fp16_adapter(engine_id=engine_id, track=track)

    @classmethod
    def checkpoints(cls, node: str, track: str | None = None, engine_id: str | None = None) -> str:
        """Legacy helper supporting existing checkpoint call patterns."""
        node_key = cls._segment(node, "node").lower()
        if node_key == "hetzner":
            if track is None:
                raise ValueError("track is required for hetzner checkpoints")
            return cls.CHECKPOINTS_HETZNER.format(track=cls._segment(track, "track"))
        if node_key == "runpod":
            if engine_id is None:
                raise ValueError("engine_id is required for runpod checkpoints")
            return cls.CHECKPOINTS_RUNPOD.format(engine_id=cls._segment(engine_id, "engine_id"))
        base = f"checkpoints/{node_key}/"
        if track is not None:
            return f"{base}{cls._segment(track, 'track')}/"
        if engine_id is not None:
            return f"{base}{cls._segment(engine_id, 'engine_id')}/"
        return base

    @classmethod
    def eval_results(cls, node: str, track: str | None = None) -> str:
        """Legacy helper preserving historical single-segment eval paths."""
        if track is None:
            return f"eval-results/{cls._segment(node, 'node')}/"
        return cls.EVAL_RESULTS.format(
            engine_id=cls._segment(node, "node"),
            track=cls._segment(track, "track"),
        )

    @staticmethod
    def gui_snapshots() -> str:
        return VaultPaths.GUI_SNAPSHOTS

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
