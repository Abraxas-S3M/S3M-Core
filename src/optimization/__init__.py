"""
S3M Phase 12 — System Optimization
Memory budget management, startup sequencing, and performance benchmarking
for Jetson AGX Orin 64GB deployment.
"""

from src.optimization.memory_budget_manager import MemoryBudgetManager
from src.optimization.performance_benchmark import PerformanceBenchmark
from src.optimization.startup_sequencer import StartupSequencer

__all__ = ["MemoryBudgetManager", "StartupSequencer", "PerformanceBenchmark"]
