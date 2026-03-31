"""Integration-test helpers for optional module availability checks."""

from __future__ import annotations

import importlib.util


def has_module(module_name: str) -> bool:
    """Return True when module is import-resolvable in this repo snapshot."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ImportError, ValueError):
        return False
