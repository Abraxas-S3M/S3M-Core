"""synapse (Matrix homeserver) integration package."""

try:
    from .adapter import SynapsematrixHomeserverAdapter
except ImportError:
    import importlib

    SynapsematrixHomeserverAdapter = importlib.import_module(
        "packages.integrations.comms.synapse-matrix-homeserver.adapter"
    ).SynapsematrixHomeserverAdapter

__all__ = ["SynapsematrixHomeserverAdapter"]
