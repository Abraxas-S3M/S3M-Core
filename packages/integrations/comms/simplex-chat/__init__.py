"""simplex-chat integration package."""

try:
    from .adapter import SimplexChatAdapter
except ImportError:
    import importlib

    SimplexChatAdapter = importlib.import_module(
        "packages.integrations.comms.simplex-chat.adapter"
    ).SimplexChatAdapter

__all__ = ["SimplexChatAdapter"]
