"""Probabilistic tactical decision engine for Layer 03 autonomy.

This package replaces brittle hardcoded rules with uncertainty-aware inference
that is more resilient in contested military sensing environments.
"""

from .belief_state import BeliefState
from .bayesian_net import BayesianThreatNet
from .particle_filter import TacticalParticleFilter
from .pomdp_solver import POMDPSolver
from .multi_objective import ParetoOptimizer
from .engine import ProbabilisticDecisionEngine

__all__ = [
    "BeliefState",
    "BayesianThreatNet",
    "TacticalParticleFilter",
    "POMDPSolver",
    "ParetoOptimizer",
    "ProbabilisticDecisionEngine",
]
