"""
S3M Layer 04 — Simulation & Wargaming
Provides simulator adapters, wargaming scenario engine, and synthetic data generation.

Subsystems:
- Adapters: Standardized connectors for Gazebo, AirSim, JSBSim, Panopticon, and custom sims
- Wargame: Scenario engine, OpFor generator (LLM-driven), After Action Review
- Synthetic: Tabular data, trajectory, and labeled threat scenario generation

Key Design:
  External simulators are NOT embedded — lightweight adapters communicate with them.
  A built-in simple physics engine provides zero-dependency fallback for all operations.
  Every simulation run is recorded as a reproducible replay artifact.
"""

from src.simulation.models import (
    AARReport,
    EntityType,
    ReplayArtifact,
    ScenarioDefinition,
    ScenarioStatus,
    SimConfig,
    SimEntity,
    SimulationState,
    SimulatorStatus,
    SyntheticDataset,
)
from src.simulation.adapters import (
    AirSimAdapter,
    BuiltinPhysicsEngine,
    GazeboAdapter,
    GenericSimAdapter,
    JSBSimAdapter,
    PanopticonAdapter,
    ReplayRecorder,
)
from src.simulation.synthetic import SyntheticDataManager
from src.simulation.wargame import AARGenerator, OpForGenerator, ScenarioEngine, ScenarioRunner

__all__ = [
    "SimulatorStatus",
    "SimulationState",
    "SimConfig",
    "SimEntity",
    "EntityType",
    "ScenarioDefinition",
    "ScenarioStatus",
    "AARReport",
    "SyntheticDataset",
    "ReplayArtifact",
    "GenericSimAdapter",
    "GazeboAdapter",
    "AirSimAdapter",
    "JSBSimAdapter",
    "PanopticonAdapter",
    "ScenarioEngine",
    "ScenarioRunner",
    "OpForGenerator",
    "AARGenerator",
    "SyntheticDataManager",
    "BuiltinPhysicsEngine",
    "ReplayRecorder",
]
