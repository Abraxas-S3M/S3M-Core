"""Manifest digest pinning for MCP tool manifests."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


def manifest_digest(tools: Iterable[Mapping[str, Any]]) -> str:
    """Compute a stable digest over tool name, description, and input schema."""
    normalized = []
    for tool in tools:
        name = str(tool.get("name", ""))
        description = str(tool.get("description", ""))
        schema = tool.get("inputSchema") or tool.get("input_schema") or {}
        normalized.append(
            {
                "name": name,
                "description": description,
                "input_schema": schema,
            }
        )
    normalized.sort(key=lambda item: item["name"])
    material = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(material).hexdigest()
