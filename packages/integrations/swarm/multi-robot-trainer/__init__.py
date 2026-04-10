"""multi_robot_trainer swarm integration package."""

try:
    from .adapter import MultiRobotTrainerAdapter
except ImportError:
    import importlib

    MultiRobotTrainerAdapter = importlib.import_module(
        "packages.integrations.swarm.multi-robot-trainer.adapter"
    ).MultiRobotTrainerAdapter

__all__ = ["MultiRobotTrainerAdapter"]
