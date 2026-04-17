"""Self-improving refinement loop for mission outcomes.

Military/tactical context:
Post-mission refinement turns operational outcomes into supervised and
preference-training examples so future command responses are safer, faster,
and more robust under contested conditions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json

from s3m_core.memory.mission_memory import Mission, MissionStep


@dataclass
class RefinementData:
    """Generated improvement artifacts from one mission."""

    sft_pairs: list[tuple[str, str]] = field(default_factory=list)
    dpo_pairs: list[tuple[str, str, str]] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    quality: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "sft_pairs": [[prompt, response] for prompt, response in self.sft_pairs],
            "dpo_pairs": [[prompt, chosen, rejected] for prompt, chosen, rejected in self.dpo_pairs],
            "lessons": list(self.lessons),
            "quality": float(self.quality),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "RefinementData":
        raw_sft = payload.get("sft_pairs", [])
        raw_dpo = payload.get("dpo_pairs", [])
        raw_lessons = payload.get("lessons", [])
        return cls(
            sft_pairs=[(str(item[0]), str(item[1])) for item in raw_sft if isinstance(item, list) and len(item) == 2],
            dpo_pairs=[
                (str(item[0]), str(item[1]), str(item[2]))
                for item in raw_dpo
                if isinstance(item, list) and len(item) == 3
            ],
            lessons=[str(item) for item in raw_lessons if str(item).strip()],
            quality=float(payload.get("quality", 0.0) or 0.0),
        )


@dataclass
class Dataset:
    """Accumulated refinement dataset filtered by quality."""

    sft_pairs: list[tuple[str, str]] = field(default_factory=list)
    dpo_pairs: list[tuple[str, str, str]] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    quality_scores: list[float] = field(default_factory=list)


class RefinementLoop:
    """Generate and persist iterative model-improvement data."""

    def __init__(self, storage_path: str = "./s3m_missions/refinement/") -> None:
        cleaned = str(storage_path).strip()
        if not cleaned:
            raise ValueError("storage_path must be non-empty")
        self.storage_path = Path(cleaned)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.dataset_path = self.storage_path / "refinement_dataset.jsonl"

    def generate_refinement_data(self, mission: Mission) -> RefinementData:
        """Generate SFT and DPO training pairs from mission transcript."""

        if not isinstance(mission, Mission):
            raise TypeError("mission must be a Mission instance")

        sft_pairs: list[tuple[str, str]] = []
        dpo_pairs: list[tuple[str, str, str]] = []
        lessons: list[str] = []

        for step in mission.steps:
            prompt = self._build_prompt(mission, step)
            chosen = self._build_better_response(mission, step)
            rejected = self._build_worse_response(step)
            sft_pairs.append((prompt, chosen))
            dpo_pairs.append((prompt, chosen, rejected))

            if step.success:
                lessons.append(f"Successful pattern: {step.description} -> {step.action_taken}")
            else:
                lessons.append(f"Failure mode: {step.description} produced {step.result}; require pre-checks.")
            if step.sae_alerts:
                lessons.append(f"Safety alerts observed on {step.step_id}: {step.sae_alerts}")

        lessons.extend(mission.lessons_learned)
        deduped_lessons = self._dedupe_preserve_order(lessons)

        data = RefinementData(sft_pairs=sft_pairs, dpo_pairs=dpo_pairs, lessons=deduped_lessons)
        data.quality = self._score_refinement_quality(data)
        return data

    def validate_refinement(self, data: RefinementData) -> bool:
        """Heuristic judge that verifies chosen responses outperform rejected ones."""

        if not isinstance(data, RefinementData):
            return False
        if not data.dpo_pairs:
            return False

        wins = 0
        for prompt, chosen, rejected in data.dpo_pairs:
            chosen_score = self._response_quality(prompt, chosen)
            rejected_score = self._response_quality(prompt, rejected)
            if chosen_score > rejected_score:
                wins += 1
        win_rate = wins / len(data.dpo_pairs)
        return win_rate >= 0.8 and data.quality >= 0.5

    def accumulate(self, data: RefinementData) -> None:
        """Persist validated refinement data for the next training cycle."""

        if not isinstance(data, RefinementData):
            raise TypeError("data must be a RefinementData instance")
        if not self.validate_refinement(data):
            raise ValueError("refinement data did not pass validation")

        row = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": data.to_dict(),
        }
        with self.dataset_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    def get_training_dataset(self, min_quality: float = 0.8) -> Dataset:
        """Return accumulated refinement data above a quality threshold."""

        try:
            threshold = float(min_quality)
        except (TypeError, ValueError) as exc:
            raise ValueError("min_quality must be numeric") from exc
        if threshold < 0.0 or threshold > 1.0:
            raise ValueError("min_quality must be between 0.0 and 1.0")
        if not self.dataset_path.exists():
            return Dataset()

        sft_pairs: list[tuple[str, str]] = []
        dpo_pairs: list[tuple[str, str, str]] = []
        lessons: list[str] = []
        quality_scores: list[float] = []

        with self.dataset_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                row = line.strip()
                if not row:
                    continue
                try:
                    payload = json.loads(row)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                item = RefinementData.from_dict(payload.get("payload", {}))
                if item.quality < threshold:
                    continue
                sft_pairs.extend(item.sft_pairs)
                dpo_pairs.extend(item.dpo_pairs)
                lessons.extend(item.lessons)
                quality_scores.append(item.quality)
        return Dataset(
            sft_pairs=sft_pairs,
            dpo_pairs=dpo_pairs,
            lessons=self._dedupe_preserve_order(lessons),
            quality_scores=quality_scores,
        )

    @staticmethod
    def _build_prompt(mission: Mission, step: MissionStep) -> str:
        return (
            f"Mission objective: {mission.objective}\n"
            f"Constraints: {', '.join(mission.constraints) if mission.constraints else 'none'}\n"
            f"Step description: {step.description}\n"
            "What should S3M do next?"
        )

    @staticmethod
    def _build_better_response(mission: Mission, step: MissionStep) -> str:
        # Tactical context: the better response prioritizes safety checks and
        # explicit objective alignment before executing high-impact actions.
        safety_clause = (
            f"Address SAE alerts first: {step.sae_alerts}. " if step.sae_alerts else "No active SAE alerts detected. "
        )
        return (
            f"Align action with objective '{mission.objective}'. "
            f"{safety_clause}"
            f"Execute: {step.action_taken}. "
            f"Expected outcome: {step.result}. "
            "Confirm constraints remain satisfied and log evidence."
        )

    @staticmethod
    def _build_worse_response(step: MissionStep) -> str:
        return (
            f"Proceed immediately with {step.action_taken} without checking constraints. "
            "Skip safety verification and do not log post-action evidence."
        )

    def _score_refinement_quality(self, data: RefinementData) -> float:
        if not data.dpo_pairs:
            return 0.0
        wins = 0
        for prompt, chosen, rejected in data.dpo_pairs:
            if self._response_quality(prompt, chosen) > self._response_quality(prompt, rejected):
                wins += 1
        base = wins / len(data.dpo_pairs)
        coverage = 1.0 if data.sft_pairs and data.lessons else 0.7
        return round(min(1.0, base * coverage), 3)

    @staticmethod
    def _response_quality(prompt: str, response: str) -> float:
        prompt_lower = prompt.lower()
        response_lower = response.lower()
        score = 0.0
        if "objective" in response_lower:
            score += 0.25
        if "constraint" in response_lower:
            score += 0.25
        if "safety" in response_lower or "sae" in response_lower:
            score += 0.25
        if "log" in response_lower or "evidence" in response_lower:
            score += 0.15
        if any(keyword in prompt_lower for keyword in ("constraint", "objective")):
            overlap = sum(1 for token in ("objective", "constraint") if token in response_lower)
            score += overlap * 0.05
        if "without checking constraints" in response_lower:
            score -= 0.35
        if "skip safety" in response_lower:
            score -= 0.35
        return score

    @staticmethod
    def _dedupe_preserve_order(items: list[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            ordered.append(text)
        return ordered
