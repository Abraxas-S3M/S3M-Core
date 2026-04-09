"""ACADOS optimal control solver integration adapter for S3M."""

from __future__ import annotations

import importlib

AcadosoptimalControlSolverAdapter = importlib.import_module(
    "packages.integrations.nato.acados-optimal-control-solver.adapter"
).AcadosoptimalControlSolverAdapter

__all__ = ["AcadosoptimalControlSolverAdapter"]
