"""detectron2 integration package."""

try:
    from .adapter import Detectron2Adapter
except ImportError:
    import importlib

    Detectron2Adapter = importlib.import_module(
        "packages.integrations.sensor_fusion.detectron2.adapter"
    ).Detectron2Adapter

__all__ = ["Detectron2Adapter"]
