"""tfc (Tinfoil Chat) integration package."""

try:
    from .adapter import TfctinfoilChatAdapter
except ImportError:
    import importlib

    TfctinfoilChatAdapter = importlib.import_module(
        "packages.integrations.comms.tfc-tinfoil-chat.adapter"
    ).TfctinfoilChatAdapter

__all__ = ["TfctinfoilChatAdapter"]
