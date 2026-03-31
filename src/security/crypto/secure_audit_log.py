"""Tamper-evident security audit logging using hash chaining."""

from __future__ import annotations

import json
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import hashlib


class SecureAuditLog:
    """Append-only JSONL log with per-entry hash chain integrity."""

    def __init__(self, log_dir: str = "data/security_audit/", max_entries_per_file: int = 10000):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries_per_file = max_entries_per_file
        self._lock = threading.Lock()
        self.previous_hash = "GENESIS"
        self._prime_previous_hash()

    def _current_log_file(self) -> Path:
        date_label = datetime.now(timezone.utc).strftime("%Y%m%d")
        return self.log_dir / f"audit_{date_label}.jsonl"

    def _iter_log_files(self) -> List[Path]:
        return sorted(self.log_dir.glob("audit_*.jsonl"))

    @staticmethod
    def _entry_hash(entry_without_hash: Dict[str, Any]) -> str:
        payload = json.dumps(entry_without_hash, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(payload).hexdigest()

    def _prime_previous_hash(self) -> None:
        files = self._iter_log_files()
        if not files:
            return
        last_file = files[-1]
        try:
            with last_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    self.previous_hash = entry.get("entry_hash", self.previous_hash)
        except Exception:
            # Defensive behavior: keep existing previous hash if log parse fails.
            pass

    def log(self, action: str, details: Dict[str, Any], severity: str = "INFO", source: str = "system") -> Dict[str, Any]:
        """Append one secure audit entry and advance hash chain."""
        if not isinstance(details, dict):
            details = {"value": str(details)}
        timestamp = datetime.now(timezone.utc).isoformat()
        base_entry = {
            "entry_id": str(uuid.uuid4()),
            "timestamp": timestamp,
            "action": action,
            "severity": severity,
            "source": source,
            "details": details,
            "previous_hash": self.previous_hash,
        }
        entry_hash = self._entry_hash(base_entry)
        entry = {**base_entry, "entry_hash": entry_hash}
        with self._lock:
            log_file = self._current_log_file()
            with log_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            self.previous_hash = entry_hash
        return entry

    def verify_chain(self, log_file: str = None) -> Dict[str, Any]:
        """Recompute and validate hash chain for one or all log files."""
        errors: List[str] = []
        first_invalid_entry: Optional[int] = None
        entries_checked = 0
        chain_previous = "GENESIS"

        files: List[Path]
        if log_file:
            files = [Path(log_file)]
        else:
            files = self._iter_log_files()

        for file in files:
            if not file.exists():
                errors.append(f"missing log file: {file}")
                continue
            with file.open("r", encoding="utf-8") as handle:
                for line_no, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    entries_checked += 1
                    try:
                        entry = json.loads(line)
                    except Exception as exc:
                        if first_invalid_entry is None:
                            first_invalid_entry = entries_checked
                        errors.append(f"{file}:{line_no}: invalid JSON: {exc}")
                        continue
                    stored_hash = entry.get("entry_hash")
                    to_hash = dict(entry)
                    to_hash.pop("entry_hash", None)
                    computed_hash = self._entry_hash(to_hash)
                    if stored_hash != computed_hash:
                        if first_invalid_entry is None:
                            first_invalid_entry = entries_checked
                        errors.append(f"{file}:{line_no}: hash mismatch")
                    previous_hash = entry.get("previous_hash")
                    if previous_hash != chain_previous:
                        if first_invalid_entry is None:
                            first_invalid_entry = entries_checked
                        errors.append(f"{file}:{line_no}: previous_hash mismatch")
                    chain_previous = stored_hash or chain_previous
        return {
            "valid": len(errors) == 0,
            "entries_checked": entries_checked,
            "first_invalid_entry": first_invalid_entry,
            "errors": errors,
        }

    def query(
        self,
        action: str = None,
        severity: str = None,
        source: str = None,
        start_time: str = None,
        end_time: str = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query recent audit entries with optional filters."""
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None
        results: List[Dict[str, Any]] = []
        for file in self._iter_log_files():
            with file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    if action and entry.get("action") != action:
                        continue
                    if severity and entry.get("severity") != severity:
                        continue
                    if source and entry.get("source") != source:
                        continue
                    if start_dt or end_dt:
                        try:
                            ts = datetime.fromisoformat(entry.get("timestamp", ""))
                        except Exception:
                            continue
                        if start_dt and ts < start_dt:
                            continue
                        if end_dt and ts > end_dt:
                            continue
                    results.append(entry)
        results.sort(key=lambda e: e.get("timestamp", ""))
        return results[-max(1, limit) :]

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate counts by severity/source and latest timestamp."""
        total = 0
        sev_counter: Counter = Counter()
        src_counter: Counter = Counter()
        latest_ts: Optional[str] = None
        for file in self._iter_log_files():
            with file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    total += 1
                    sev_counter.update([entry.get("severity", "UNKNOWN")])
                    src_counter.update([entry.get("source", "unknown")])
                    ts = entry.get("timestamp")
                    if ts and (latest_ts is None or ts > latest_ts):
                        latest_ts = ts
        return {
            "total_entries": total,
            "entries_by_severity": dict(sev_counter),
            "entries_by_source": dict(src_counter),
            "latest_entry_timestamp": latest_ts,
        }

    def export(self, filepath: str) -> None:
        """Export all audit entries to a single JSON array file."""
        entries = self.query(limit=10_000_000)
        out = Path(filepath)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            json.dump(entries, handle, indent=2, ensure_ascii=False)
