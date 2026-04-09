"""BackBlaze B2 connector shim for tactical snapshot publishing.

Military/tactical context:
When cloud credentials are unavailable during field rehearsals, this connector
still persists snapshot artifacts locally so operators can validate GUI payloads
offline before syncing to remote object storage.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class B2Connector:
    """Persist JSON objects using a B2-compatible upload interface."""

    _OBJECT_KEY_PATTERN = re.compile(r"^[A-Za-z0-9._/-]+$")

    def __init__(self, mirror_root: str | Path | None = None) -> None:
        root = Path(mirror_root) if mirror_root is not None else Path("state/gui_bridge/b2_mirror")
        self._mirror_root = root.resolve()
        self._mirror_root.mkdir(parents=True, exist_ok=True)

    def upload_json(self, object_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Upload one JSON object and return upload metadata."""
        content = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        return self.upload_bytes(object_key=object_key, content=content, content_type="application/json")

    def upload_bytes(self, object_key: str, content: bytes, content_type: str = "application/octet-stream") -> Dict[str, Any]:
        """Upload raw bytes and return ETag/timestamp metadata."""
        safe_key = self._validate_object_key(object_key)
        destination = (self._mirror_root / safe_key).resolve()
        if self._mirror_root not in destination.parents and destination != self._mirror_root:
            raise ValueError("object_key resolves outside configured mirror root")

        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)

        etag = hashlib.md5(content).hexdigest()
        uploaded_at = datetime.now(timezone.utc).isoformat()
        return {
            "object_key": safe_key,
            "etag": etag,
            "uploaded_at": uploaded_at,
            "size_bytes": len(content),
            "content_type": content_type,
        }

    @classmethod
    def from_env(cls) -> "B2Connector":
        mirror_root = Path("state/gui_bridge/b2_mirror")
        return cls(mirror_root=mirror_root)

    def _validate_object_key(self, object_key: str) -> str:
        candidate = str(object_key or "").strip()
        if not candidate:
            raise ValueError("object_key is required")
        if candidate.startswith("/") or ".." in Path(candidate).parts:
            raise ValueError("object_key must be relative and must not contain parent traversal")
        if not self._OBJECT_KEY_PATTERN.fullmatch(candidate):
            raise ValueError("object_key contains invalid characters")
        return candidate
