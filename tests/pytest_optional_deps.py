"""
Pytest plugin: skip test modules cleanly when optional edge dependencies are absent.

Tactical CI on Jetson-class agents often omits PyTorch and full API stacks; collection
must not fail before skip markers can run.
"""

from __future__ import annotations

import ast
import importlib.util
from collections.abc import Iterator
from pathlib import Path

import pytest

_TORCH_ROOTS = frozenset({"torch", "torchvision", "torchaudio"})
_FASTAPI_ROOTS = frozenset({"fastapi", "starlette"})


def _import_roots(path: Path) -> set[str]:
    """Return top-level package roots imported at module scope."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        return set()

    roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _missing_dependency_reason(path: Path) -> str | None:
    roots = _import_roots(path)
    if roots & _TORCH_ROOTS and importlib.util.find_spec("torch") is None:
        return (
            "PyTorch (torch) is not installed — skipping GPU/ML tests "
            "(optional; install requirements-inference.txt or requirements-gpu-training.txt)"
        )
    if roots & _FASTAPI_ROOTS and importlib.util.find_spec("fastapi") is None:
        return (
            "FastAPI is not installed — skipping API integration tests "
            "(optional; pip install -r requirements-api.txt)"
        )
    return None


def _cuda_available() -> bool:
    try:
        import torch  # type: ignore[import-not-found]
    except ImportError:
        return False
    return bool(torch.cuda.is_available())


class _OptionalDependencySkippedModule(pytest.Module):
    """Collect a single skipped placeholder instead of importing the test module."""

    def __init__(self, skip_reason: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._skip_reason = skip_reason

    def _getobj(self) -> None:
        return None

    def collect(self) -> Iterator[pytest.Item]:
        reason = self._skip_reason

        def _skip() -> None:
            pytest.skip(reason)

        yield pytest.Function.from_parent(
            self,
            name="optional_dependency_skip",
            callobj=_skip,
        )


@pytest.hookimpl(tryfirst=True)
def pytest_pycollect_makemodule(module_path: Path, parent: pytest.Collector):
    if not (module_path.name.startswith("test_") or module_path.name.endswith("_test.py")):
        return None
    reason = _missing_dependency_reason(module_path)
    if reason is None:
        return None
    return _OptionalDependencySkippedModule.from_parent(
        parent,
        path=module_path,
        skip_reason=reason,
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Apply gpu marker skips and auto-tag torch-backed modules when torch is present."""
    del config
    torch_installed = importlib.util.find_spec("torch") is not None

    if torch_installed:
        for item in items:
            if item.name == "optional_dependency_skip":
                continue
            mod_path = Path(str(getattr(item, "path", item.fspath)))
            if mod_path.suffix != ".py":
                continue
            if _import_roots(mod_path) & _TORCH_ROOTS and not item.get_closest_marker("gpu"):
                item.add_marker(pytest.mark.gpu)

    for item in items:
        if item.name == "optional_dependency_skip":
            continue
        if item.get_closest_marker("gpu"):
            if not torch_installed:
                item.add_marker(
                    pytest.mark.skip(
                        reason="gpu marker: PyTorch not installed on this node",
                    )
                )
            elif not _cuda_available():
                item.add_marker(
                    pytest.mark.skip(
                        reason="gpu marker: CUDA device not available",
                    )
                )
