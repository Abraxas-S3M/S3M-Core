"""
Canonical vault key templates for B2-backed artifact storage.

Tactical context:
    Stable key conventions guarantee that operators, training pipelines, and
    edge runtimes all reference the same mission artifact coordinates.
"""

from __future__ import annotations

from typing import Final


class VaultPaths:
    """Structured B2 object key templates for sovereign artifact placement.

    Tactical context:
        Consistent key derivation is required so model promotion, restore,
        and mission pre-positioning workflows can execute without ambiguity
        under degraded communications.
    """

    FP16_BASE: Final[str] = "models/fp16/{engine_id}/"
    Q4_SERVING: Final[str] = "models/q4-gguf/{engine_id}/"
    FP16_ADAPTER: Final[str] = "models/fp16-adapters/{engine_id}/{track}/"
    FP16_MERGED: Final[str] = "models/fp16-merged/{engine_id}/{track}/"
    DATASETS: Final[str] = "datasets/{track}/"
    SCENARIO_PACKS: Final[str] = "datasets/{track}/scenarios/"
    CHECKPOINTS_HETZNER: Final[str] = "checkpoints/hetzner/{track}/"
    CHECKPOINTS_RUNPOD: Final[str] = "checkpoints/runpod/{engine_id}/"
    EVAL_RESULTS: Final[str] = "eval-results/{engine_id}/{track}/"
    GROK_VERDICTS_PENDING: Final[str] = "grok-verdicts/pending/"
    GROK_VERDICTS_APPROVED: Final[str] = "grok-verdicts/approved/"
    GROK_VERDICTS_REJECTED: Final[str] = "grok-verdicts/rejected/"
    GUI_SNAPSHOTS: Final[str] = "gui-snapshots/"

    BLOCKED_ENGINES: Final[frozenset[str]] = frozenset({"grok-300b"})

    @classmethod
    def fp16_base(cls, engine_id: str) -> str:
        return cls.FP16_BASE.format(engine_id=engine_id.strip())

    @classmethod
    def q4_serving(cls, engine_id: str) -> str:
        return cls.Q4_SERVING.format(engine_id=engine_id.strip())

    @classmethod
    def fp16_adapter(cls, engine_id: str, track: str) -> str:
        return cls.FP16_ADAPTER.format(engine_id=engine_id.strip(), track=track.strip())

    @classmethod
    def fp16_merged(cls, engine_id: str, track: str) -> str:
        return cls.FP16_MERGED.format(engine_id=engine_id.strip(), track=track.strip())

    @classmethod
    def datasets_track(cls, track: str) -> str:
        return cls.DATASETS.format(track=track.strip())

    @classmethod
    def scenario_packs(cls, track: str) -> str:
        return cls.SCENARIO_PACKS.format(track=track.strip())

    @classmethod
    def dataset_scenarios(cls, track: str) -> str:
        """Compatibility alias for scenario pack prefix resolution."""
        return cls.scenario_packs(track)

    @classmethod
    def quantized_engine(cls, engine_id: str) -> str:
        """Compatibility alias for deployable Q4 model prefix."""
        return cls.q4_serving(engine_id)

    @classmethod
    def adapters(cls, engine_id: str, track: str | None = None) -> str:
        """Compatibility helper matching legacy adapter prefix calls."""
        if track is None:
            return cls.FP16_ADAPTER.format(engine_id=engine_id.strip(), track="")
        return cls.fp16_adapter(engine_id, track)

    @classmethod
    def checkpoints(cls, node_id: str, track: str | None = None, engine_id: str | None = None) -> str:
        """Compatibility helper for checkpoint path conventions."""
        node = node_id.strip().lower()
        if node == "runpod":
            if not engine_id:
                raise ValueError("engine_id is required for runpod checkpoint paths")
            return cls.CHECKPOINTS_RUNPOD.format(engine_id=engine_id.strip())
        if not track:
            raise ValueError("track is required for non-runpod checkpoint paths")
        return cls.CHECKPOINTS_HETZNER.format(track=track.strip())

    @classmethod
    def eval_results(cls, engine_or_node: str, track: str = "global") -> str:
        """Compatibility helper for evaluation payload storage."""
        return cls.EVAL_RESULTS.format(engine_id=engine_or_node.strip(), track=track.strip())

    @classmethod
    def gui_snapshots(cls) -> str:
        """Return GUI snapshot prefix."""
        return cls.GUI_SNAPSHOTS

    @staticmethod
    def contains_blocked_token(path_value: str, blocked_tokens: list[str] | tuple[str, ...]) -> bool:
        """Return True when one blocked token is present in path text."""
        lowered = path_value.lower()
        return any(token.lower() in lowered for token in blocked_tokens if token)

    @classmethod
    def is_blocked_engine(cls, engine_id: str) -> bool:
        return engine_id.strip() in cls.BLOCKED_ENGINES


VAULT_PATHS = {
    "base_weights": VaultPaths.FP16_BASE,
    "quantized": VaultPaths.Q4_SERVING,
    "datasets": VaultPaths.DATASETS,
    "adapters": VaultPaths.FP16_ADAPTER,
    "checkpoints_hetzner": VaultPaths.CHECKPOINTS_HETZNER,
    "checkpoints_runpod": VaultPaths.CHECKPOINTS_RUNPOD,
    "eval_results": VaultPaths.EVAL_RESULTS,
    "grok_verdicts_pending": VaultPaths.GROK_VERDICTS_PENDING,
    "grok_verdicts_approved": VaultPaths.GROK_VERDICTS_APPROVED,
    "grok_verdicts_rejected": VaultPaths.GROK_VERDICTS_REJECTED,
    "gui_snapshots": VaultPaths.GUI_SNAPSHOTS,
    "scenario_packs": VaultPaths.SCENARIO_PACKS,
}
