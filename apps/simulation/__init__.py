"""
S3M Layer 12 — Training & Simulation Advanced
LLM-powered wargaming suite with officer education, exercise management,
and multi-engine battle simulation.

Subsystems:
- Wargaming Suite: LLM-driven adversaries, multi-agent conflict simulation, COA testing
- Scenario Authoring: ORBAT → MSDL → scenario → simulation pipeline
- Exercise Framework: Multi-phase exercises with DIS/C2SIM distributed participation
- Battle Visualization: 2D tactical map replay with unit movement and engagement
- Training Portal: Officer courses, wargame assignments, scoring, certification
- Cyber Range: SOC training integration from Phase 13
- After Action: LLM-generated AAR with lessons learned and performance scoring

Data Flow:
  ORBAT (Phase 16) → Scenario Authoring → Wargame Engine → DIS/C2SIM (Phase 16)
  → AAR (Phase 7) → Training Score → Officer Record → Dashboard (Phase 6)
  Cyber exercises (Phase 13) → Training Score → Officer Record
"""

from apps.simulation.battle_visualizer import BattleVisualizer
from apps.simulation.cyber_range import CyberRangeIntegrator
from apps.simulation.exercises import ExerciseFramework
from apps.simulation.manager import TrainingSimManager
from apps.simulation.models import (
    AdversaryProfile,
    Assignment,
    Course,
    CourseModule,
    Exercise,
    ExercisePhase,
    ExerciseScore,
    OfficerRecord,
    WargameConfig,
    WargameResult,
    WargameSession,
    WargameTurn,
)
from apps.simulation.scenario_author import ScenarioAuthor
from apps.simulation.training import TrainingPortal
from apps.simulation.wargaming import LLMAdversary, WargameSuite

__all__ = [
    "TrainingSimManager",
    "WargameSuite",
    "WargameSession",
    "WargameConfig",
    "WargameTurn",
    "WargameResult",
    "LLMAdversary",
    "AdversaryProfile",
    "ScenarioAuthor",
    "ExerciseFramework",
    "Exercise",
    "ExercisePhase",
    "ExerciseScore",
    "TrainingPortal",
    "OfficerRecord",
    "Course",
    "CourseModule",
    "Assignment",
    "BattleVisualizer",
    "CyberRangeIntegrator",
]
