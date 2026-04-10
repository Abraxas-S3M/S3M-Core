"""mavsdk_drone_show integration adapter package for S3M."""

try:
    from .adapter import MavsdkDroneShowAdapter
except ImportError:
    import importlib

    MavsdkDroneShowAdapter = importlib.import_module(
        "packages.integrations.swarm.mavsdk-drone-show.adapter"
    ).MavsdkDroneShowAdapter

__all__ = ["MavsdkDroneShowAdapter"]

