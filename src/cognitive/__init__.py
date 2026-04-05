"""
S3M Unified Cognitive Engine — The Central Brain
=================================================
Replaces distributed decision logic with a unified cognitive architecture
that maintains belief states, reasons under uncertainty, and resolves
conflicting objectives through principled probabilistic inference.

Architecture:
  Sensors → WorldModel → BeliefState → CognitiveEngine → ActionSelection
                ↑                              ↓
         MemorySystem ←── DecisionJournal ←── Outcome
"""

from src.cognitive.unified_cognitive_engine import (
    UnifiedCognitiveEngine,
    CognitiveConfig,
    CognitiveState,
    CognitiveDecision,
    ThinkCycle,
)
from src.cognitive.world_model import (
    BayesianWorldModel,
    WorldState,
    WorldHypothesis,
    WorldObservation,
    CausalLink,
)
from src.cognitive.multi_objective_resolver import (
    MultiObjectiveResolver,
    ObjectiveSpec,
    ConflictReport,
    ParetoSolution,
    ResolutionStrategy,
)

__all__ = [
    "UnifiedCognitiveEngine",
    "CognitiveConfig",
    "CognitiveState",
    "CognitiveDecision",
    "ThinkCycle",
    "BayesianWorldModel",
    "WorldState",
    "WorldHypothesis",
    "WorldObservation",
    "CausalLink",
    "MultiObjectiveResolver",
    "ObjectiveSpec",
    "ConflictReport",
    "ParetoSolution",
    "ResolutionStrategy",
]
