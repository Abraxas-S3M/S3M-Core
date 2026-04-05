"""Simple evolution loop for adaptive edge policy exploration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Sequence


@dataclass(frozen=True)
class EvolutionCandidate:
    """Candidate genome with deterministic score for mission adaptation."""

    genome: Sequence[float]
    score: float


@dataclass(frozen=True)
class EvolutionStepResult:
    """Explicit loop step result for compatibility with higher-level runtimes."""

    best_genome: Sequence[float]
    best_score: float


@dataclass
class EvolutionLoop:
    """
    Minimal evolutionary optimizer for disconnected adaptation cycles.

    The implementation is intentionally lightweight so it can run offline on
    austere hardware without external services.
    """

    scorer: Callable[[Sequence[float]], float]
    elite_size: int = 2
    history: List[EvolutionStepResult] = field(default_factory=list)

    def step(self, population: Iterable[Sequence[float]]) -> EvolutionStepResult:
        candidates = [
            EvolutionCandidate(genome=tuple(genome), score=float(self.scorer(genome)))
            for genome in population
        ]
        if not candidates:
            raise ValueError("population must contain at least one genome")

        candidates.sort(key=lambda item: item.score, reverse=True)
        elite = candidates[: max(1, self.elite_size)]
        winner = EvolutionStepResult(
            best_genome=tuple(elite[0].genome),
            best_score=float(elite[0].score),
        )
        self.history.append(winner)
        if len(self.history) > 1024:
            self.history = self.history[-1024:]
        return winner
