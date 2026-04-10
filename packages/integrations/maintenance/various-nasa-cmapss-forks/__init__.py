"""Various NASA CMAPSS forks maintenance integration wrapper."""

try:
    from .adapter import VariousNasaCmapssForksAdapter
except ImportError:  # pragma: no cover - direct-path pytest collection fallback
    import importlib.util
    from pathlib import Path

    _adapter_path = Path(__file__).resolve().parent / "adapter.py"
    _spec = importlib.util.spec_from_file_location("s3m_maintenance_various_nasa_cmapss_adapter", _adapter_path)
    if _spec is None or _spec.loader is None:
        raise ImportError(f"Unable to load adapter module at {_adapter_path}")
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
    VariousNasaCmapssForksAdapter = _module.VariousNasaCmapssForksAdapter

__all__ = ["VariousNasaCmapssForksAdapter"]
