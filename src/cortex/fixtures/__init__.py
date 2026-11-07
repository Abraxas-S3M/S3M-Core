"""Deterministic Cortex topology fixtures for unit tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from src.cortex.fixtures.cctv import build_cctv_twin

# Legacy reachability graph lives in sibling ``fixtures.py`` (shadowed by this package).
_fixtures_py = Path(__file__).resolve().parent.parent / "fixtures.py"
_spec = importlib.util.spec_from_file_location("src.cortex._fixtures_py", _fixtures_py)
assert _spec and _spec.loader
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)
cctv_reachability_graph = _legacy.cctv_reachability_graph

__all__ = ["build_cctv_twin", "cctv_reachability_graph"]
