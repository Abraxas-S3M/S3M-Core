"""BackBlaze object-storage connector with offline filesystem emulation.

Military/tactical context:
This connector preserves a deterministic artifact flow when internet links are
degraded. Hetzner-side jobs can keep operating against a local mirror while
retaining the same object-key semantics used for B2 promotion lanes.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


class B2Connector:
    """Minimal B2 connector API for training artifact orchestration.

    The implementation intentionally uses a filesystem-backed emulation root to
    keep unit tests and disconnected deployments functional with zero network
    dependency. Object keys are mapped to paths under ``emulation_root``.
    """

    def __init__(self, emulation_root: Path | str | None = None) -> None:
        root = emulation_root if emulation_root is not None else "/workspace/.b2_emulation"
        self.emulation_root = Path(root).resolve()
        self.emulation_root.mkdir(parents=True, exist_ok=True)

    def list_keys(self, prefix: str = "") -> list[str]:
        """List object keys beneath a prefix."""
        normalized = prefix.strip("/")
        if normalized:
            anchor = self.emulation_root / normalized
            if not anchor.exists():
                return []
            if anchor.is_file():
                return [normalized]
            base = anchor
        else:
            base = self.emulation_root

        keys: list[str] = []
        for candidate in base.rglob("*"):
            if candidate.is_file():
                keys.append(candidate.relative_to(self.emulation_root).as_posix())
        return sorted(keys)

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def get_bytes(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def put_bytes(self, key: str, payload: bytes) -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return key

    def get_text(self, key: str, encoding: str = "utf-8") -> str:
        return self._resolve(key).read_text(encoding=encoding)

    def put_text(self, key: str, payload: str, encoding: str = "utf-8") -> str:
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding=encoding)
        return key

    def get_json(self, key: str) -> Any:
        return json.loads(self.get_text(key))

    def put_json(self, key: str, payload: Any) -> str:
        return self.put_text(key, json.dumps(payload, ensure_ascii=False, indent=2))

    def stat_size(self, key: str) -> int:
        return int(self._resolve(key).stat().st_size)

    def move(self, source_key: str, destination_key: str) -> str:
        source = self._resolve(source_key)
        destination = self._resolve(destination_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        source.replace(destination)
        return destination_key

    def copy(self, source_key: str, destination_key: str) -> str:
        source = self._resolve(source_key)
        destination = self._resolve(destination_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination_key

    def delete(self, key: str) -> None:
        target = self._resolve(key)
        if target.exists():
            target.unlink()

    def _resolve(self, key: str) -> Path:
        safe_key = key.lstrip("/")
        return self.emulation_root / safe_key
