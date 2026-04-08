"""Domain-partitioned JSONL data lake writer with DVC rotation hooks."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

_PART_FILE_PATTERN = re.compile(r"^part-(\d{6})\.jsonl$")


class DataLake:
    """Persist training rows by domain for offline tactical retraining."""

    def __init__(
        self,
        base_dir: str | Path = "/mnt/s3m-weights/datasets",
        *,
        max_file_size_bytes: int = 100 * 1024 * 1024,
        source: str | None = None,
        dvc_executable: str = "dvc",
    ) -> None:
        self.base_dir = Path(base_dir)
        self.max_file_size_bytes = int(max_file_size_bytes)
        self.source = source
        self.dvc_executable = dvc_executable
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        domain: str,
        input_text: Any,
        output_text: Any,
        language: str = "en",
    ) -> Path:
        safe_domain = self._sanitize_domain(domain)
        domain_dir = self.base_dir / safe_domain
        domain_dir.mkdir(parents=True, exist_ok=True)

        record = {
            "domain": safe_domain,
            "input": self._normalize_value(input_text),
            "output": self._normalize_value(output_text),
            "language": str(language),
            "timestamp": time.time(),
        }
        if self.source:
            record["source"] = self.source

        payload = json.dumps(record, ensure_ascii=False) + "\n"
        payload_size = len(payload.encode("utf-8"))
        target_file = self._active_file(domain_dir)

        if target_file.exists() and target_file.stat().st_size + payload_size > self.max_file_size_bytes:
            # Freeze completed tactical corpus slices into DVC before opening a new shard.
            self._dvc_add(target_file)
            target_file = self._next_file(domain_dir, target_file)

        with target_file.open("a", encoding="utf-8") as handle:
            handle.write(payload)

        return target_file

    def _active_file(self, domain_dir: Path) -> Path:
        parts = self._list_parts(domain_dir)
        if not parts:
            return domain_dir / "part-000001.jsonl"
        return parts[-1]

    def _next_file(self, domain_dir: Path, current_file: Path) -> Path:
        match = _PART_FILE_PATTERN.match(current_file.name)
        if not match:
            return domain_dir / "part-000001.jsonl"
        next_idx = int(match.group(1)) + 1
        return domain_dir / f"part-{next_idx:06d}.jsonl"

    def _list_parts(self, domain_dir: Path) -> list[Path]:
        indexed_paths: list[tuple[int, Path]] = []
        for path in domain_dir.glob("part-*.jsonl"):
            match = _PART_FILE_PATTERN.match(path.name)
            if not match:
                continue
            indexed_paths.append((int(match.group(1)), path))
        indexed_paths.sort(key=lambda item: item[0])
        return [path for _, path in indexed_paths]

    def _dvc_add(self, file_path: Path) -> None:
        if not file_path.exists():
            return
        try:
            subprocess.run(
                [self.dvc_executable, "add", str(file_path)],
                check=True,
                capture_output=True,
                text=True,
                cwd=self.base_dir,
                timeout=120,
            )
        except Exception:
            # DVC failures must not interrupt tactical data capture.
            return

    @staticmethod
    def _sanitize_domain(domain: str) -> str:
        safe_domain = "".join(ch for ch in str(domain) if ch.isalnum() or ch in ("_", "-")).strip()
        return safe_domain or "unknown"

    @staticmethod
    def _normalize_value(value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        try:
            json.dumps(value)
        except TypeError:
            return str(value)
        return value
