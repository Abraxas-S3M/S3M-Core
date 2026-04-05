"""Unit tests for edge-safe evolution loop integration."""

from src.evolution import EvolutionCandidate, EvolutionLoop
from src.evolution.loop import EvolutionStepResult


def test_evolution_loop_step_returns_best_candidate() -> None:
    scorer = lambda genome: float(sum(genome))
    loop = EvolutionLoop(scorer=scorer, elite_size=2)
    winner = loop.step([[0.1, 0.2], [0.6, 0.3], [0.2, 0.1]])
    assert isinstance(winner, EvolutionStepResult)
    assert tuple(winner.best_genome) == (0.6, 0.3)
    assert winner.best_score == 0.8999999999999999


def test_evolution_loop_rejects_empty_population() -> None:
    loop = EvolutionLoop(scorer=lambda genome: 0.0)
    try:
        loop.step([])
    except ValueError as exc:
        assert "population" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
