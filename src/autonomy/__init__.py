"""
S3M Layer 03 — Autonomy and Swarm
Provides reinforcement learning agent management, behavior tree mission execution,
multi-agent swarm coordination, and explainable AI assurance for autonomous decisions.

Subsystems:
- RL: Agent training and policy management (Ray RLlib / Stable-Baselines3)
- Behavior Trees: OODA-loop mission execution with LLM replanning
- Swarm: Multi-agent coordination, formations, task allocation, NL commands
- XAI: Decision logging, feature attribution, human-review gating

Data Flow:
  ThreatEvents (Layer 02) → LLM Assessment (Layer 01) → Autonomy Decisions (Layer 03)
  Autonomy Commands → Navigation (Layer 05) / Simulation (Layer 04)
"""

from .models import (
    AgentState,
    AgentRole,
    AgentInfo,
    Mission,
    MissionStatus,
    MissionType,
    SwarmCommand,
    CommandType,
    Formation,
    FormationType,
    AutonomyDecision,
    DecisionType,
)
from .decision_engine import (
    BeliefState,
    BayesianThreatNet,
    TacticalParticleFilter,
    POMDPSolver,
    ParetoOptimizer,
    ProbabilisticDecisionEngine,
)
from .arbitration import (
    CoalitionEngine,
    AuctionAllocator,
    ByzantineConsensus,
    ConflictResolver,
    MultiAgentArbitrator,
)
from .realtime_arbiter import (
    TacticalPriority,
    PriorityManager,
    RiskAssessor,
    ReplanDirective,
    OnlineReplanner,
    RealtimeDecisionArbiter,
)

__all__ = [
    "AgentState",
    "AgentRole",
    "AgentInfo",
    "Mission",
    "MissionStatus",
    "MissionType",
    "SwarmCommand",
    "CommandType",
    "Formation",
    "FormationType",
    "AutonomyDecision",
    "DecisionType",
    "BeliefState",
    "BayesianThreatNet",
    "TacticalParticleFilter",
    "POMDPSolver",
    "ParetoOptimizer",
    "ProbabilisticDecisionEngine",
    "CoalitionEngine",
    "AuctionAllocator",
    "ByzantineConsensus",
    "ConflictResolver",
    "MultiAgentArbitrator",
    "TacticalPriority",
    "PriorityManager",
    "RiskAssessor",
    "ReplanDirective",
    "OnlineReplanner",
    "RealtimeDecisionArbiter",
]
