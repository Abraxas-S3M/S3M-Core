"""chatmail/relay comms integration wrapper for S3M."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_adapter_class():
    adapter_path = Path(__file__).resolve().parent / "adapter.py"
    spec = importlib.util.spec_from_file_location("s3m_chatmail_relay_adapter", adapter_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load adapter module from {adapter_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ChatmailrelayAdapter


ChatmailrelayAdapter = _load_adapter_class()

__all__ = ["ChatmailrelayAdapter"]
