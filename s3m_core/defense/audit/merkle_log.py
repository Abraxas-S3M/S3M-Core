"""Immutable audit chain with Merkle-assisted integrity checks.

Military/tactical context:
Forward-deployed autonomous agents can become partially compromised. This log
maintains a tamper-evident evidence chain so SOC operators can prove whether
events were altered after capture.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import csv
import hashlib
import io
import json
import os
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List


_GENESIS_HASH = "GENESIS"
_ENTRY_FIELDS = (
    "timestamp",
    "session_id",
    "event_type",
    "source_layer",
    "severity",
    "details",
    "previous_hash",
)


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


def _parse_iso8601(timestamp_raw: str) -> datetime:
    value = str(timestamp_raw).strip()
    if not value:
        raise ValueError("timestamp is required")
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    return _ensure_utc(parsed)


@dataclass(slots=True, frozen=True)
class AuditEntry:
    """One audit record submitted by a defense subsystem."""

    timestamp: datetime
    session_id: str
    event_type: str
    source_layer: str
    severity: str
    details: Dict[str, Any]
    previous_hash: str

    def __post_init__(self) -> None:
        if not str(self.session_id).strip():
            raise ValueError("session_id must be non-empty")
        if not str(self.event_type).strip():
            raise ValueError("event_type must be non-empty")
        if not str(self.source_layer).strip():
            raise ValueError("source_layer must be non-empty")
        if not str(self.severity).strip():
            raise ValueError("severity must be non-empty")
        if not isinstance(self.details, dict):
            raise TypeError("details must be a dictionary")

    def to_payload(self, previous_hash: str) -> Dict[str, Any]:
        return {
            "timestamp": _ensure_utc(self.timestamp).isoformat(),
            "session_id": str(self.session_id).strip(),
            "event_type": str(self.event_type).strip(),
            "source_layer": str(self.source_layer).strip(),
            "severity": str(self.severity).strip().lower(),
            "details": dict(self.details),
            "previous_hash": previous_hash,
        }


@dataclass(slots=True, frozen=True)
class IntegrityReport:
    """Result of full-chain integrity validation."""

    entries_verified: int
    chain_intact: bool
    first_broken_entry: int | None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entries_verified": int(self.entries_verified),
            "chain_intact": bool(self.chain_intact),
            "first_broken_entry": self.first_broken_entry,
        }


class MerkleAuditLog:
    """Append-only tamper-evident log with chained and Merkle verification.

    Deployment model:
    - Agent/container process should only have append permission to ``log_path``.
    - Separate forensic verifier process should run ``verify_integrity`` and
      ``export`` with read access from outside the mutable agent context.
    """

    def __init__(self, log_path: str, hash_algorithm: str = "sha256") -> None:
        if not str(log_path).strip():
            raise ValueError("log_path must be non-empty")
        algorithm = str(hash_algorithm).strip().lower()
        try:
            hashlib.new(algorithm)
        except ValueError as exc:
            raise ValueError(f"Unsupported hash algorithm: {hash_algorithm}") from exc

        self.log_path = Path(log_path)
        self.hash_algorithm = algorithm
        self._lock = RLock()
        self._last_hash = _GENESIS_HASH
        self._leaf_hashes: List[str] = []
        self._entry_count = 0
        self._readable = True

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._prime_state()

    def append(self, entry: AuditEntry) -> str:
        """Append one entry and return its cryptographic hash."""
        if not isinstance(entry, AuditEntry):
            raise TypeError("entry must be an AuditEntry instance")

        with self._lock:
            supplied_previous = str(entry.previous_hash or "").strip()
            if not self._readable and not supplied_previous:
                raise ValueError(
                    "previous_hash is required when log is write-only and cannot be read"
                )
            previous_hash = supplied_previous or self._last_hash
            if self._readable and previous_hash != self._last_hash:
                raise ValueError(
                    "previous_hash mismatch: expected "
                    f"{self._last_hash!r}, received {previous_hash!r}"
                )

            payload = entry.to_payload(previous_hash=previous_hash)
            entry_hash = self._hash_payload(payload)
            updated_leaves = [*self._leaf_hashes, entry_hash]
            merkle_root = self._compute_merkle_root(updated_leaves) if self._readable else ""
            serialized = {
                **payload,
                "entry_hash": entry_hash,
                "merkle_root": merkle_root,
            }
            self._append_json_line(serialized)
            self._last_hash = entry_hash
            self._leaf_hashes = updated_leaves
            self._entry_count += 1
            return entry_hash

    def verify_integrity(self) -> IntegrityReport:
        """Walk the full log and validate chained + Merkle integrity."""
        with self._lock:
            if not self.log_path.exists():
                return IntegrityReport(entries_verified=0, chain_intact=True, first_broken_entry=None)

            chain_previous = _GENESIS_HASH
            leaves: List[str] = []
            entries_verified = 0
            first_broken_entry: int | None = None

            try:
                with self.log_path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        stripped = line.strip()
                        if not stripped:
                            continue
                        entries_verified += 1
                        try:
                            record = json.loads(stripped)
                        except (TypeError, ValueError, json.JSONDecodeError):
                            if first_broken_entry is None:
                                first_broken_entry = entries_verified
                            break

                        try:
                            payload = self._payload_from_record(record)
                        except (TypeError, ValueError):
                            if first_broken_entry is None:
                                first_broken_entry = entries_verified
                            break
                        computed_hash = self._hash_payload(payload)
                        stored_hash = str(record.get("entry_hash", "")).strip()
                        stored_previous = str(record.get("previous_hash", "")).strip()
                        stored_root = str(record.get("merkle_root", "")).strip()

                        if stored_previous != chain_previous and first_broken_entry is None:
                            first_broken_entry = entries_verified
                        if stored_hash != computed_hash and first_broken_entry is None:
                            first_broken_entry = entries_verified

                        leaves.append(stored_hash or computed_hash)
                        expected_root = self._compute_merkle_root(leaves)
                        if stored_root and stored_root != expected_root and first_broken_entry is None:
                            first_broken_entry = entries_verified

                        chain_previous = stored_hash or computed_hash
            except (PermissionError, OSError) as exc:
                raise PermissionError(
                    "verify_integrity requires read access to the immutable log file"
                ) from exc

            return IntegrityReport(
                entries_verified=entries_verified,
                chain_intact=first_broken_entry is None,
                first_broken_entry=first_broken_entry,
            )

    def export(self, start: datetime, end: datetime, format: str = "json") -> str:
        """Export entries in a UTC time range for external forensics."""
        if not isinstance(start, datetime):
            raise TypeError("start must be a datetime")
        if not isinstance(end, datetime):
            raise TypeError("end must be a datetime")
        start_utc = _ensure_utc(start)
        end_utc = _ensure_utc(end)
        if start_utc > end_utc:
            raise ValueError("start must be <= end")

        fmt = str(format or "json").strip().lower()
        if fmt not in {"json", "jsonl", "csv"}:
            raise ValueError("format must be one of: json, jsonl, csv")

        selected: List[Dict[str, Any]] = []
        with self._lock:
            try:
                for record in self._iter_records():
                    timestamp = _parse_iso8601(str(record.get("timestamp", "")))
                    if start_utc <= timestamp <= end_utc:
                        selected.append(record)
            except (PermissionError, OSError) as exc:
                raise PermissionError(
                    "export requires read access to the immutable log file"
                ) from exc

        if fmt == "json":
            return json.dumps(selected, indent=2, ensure_ascii=False, sort_keys=True)
        if fmt == "jsonl":
            if not selected:
                return ""
            return "\n".join(
                json.dumps(record, ensure_ascii=False, sort_keys=True) for record in selected
            ) + "\n"
        return self._to_csv(selected)

    def _prime_state(self) -> None:
        if not self.log_path.exists():
            return

        try:
            for record in self._iter_records():
                entry_hash = str(record.get("entry_hash", "")).strip()
                if not entry_hash:
                    continue
                self._last_hash = entry_hash
                self._leaf_hashes.append(entry_hash)
                self._entry_count += 1
        except (PermissionError, OSError):
            # Write-only deployments cannot read previous entries from inside
            # the container. Integrity checks must run in an external verifier.
            self._readable = False

    def _iter_records(self) -> Iterable[Dict[str, Any]]:
        if not self.log_path.exists():
            return []
        records: List[Dict[str, Any]] = []
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    records.append(json.loads(stripped))
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
        return records

    def _append_json_line(self, payload: Dict[str, Any]) -> None:
        encoded_line = json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n"
        fd = os.open(self.log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o640)
        try:
            os.write(fd, encoded_line.encode("utf-8"))
        finally:
            os.close(fd)

    def _hash_payload(self, payload: Dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.new(self.hash_algorithm)
        digest.update(canonical.encode("utf-8"))
        return digest.hexdigest()

    def _payload_from_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        for field_name in _ENTRY_FIELDS:
            if field_name == "timestamp":
                payload[field_name] = _parse_iso8601(str(record.get(field_name, ""))).isoformat()
            elif field_name == "details":
                details = record.get(field_name, {})
                if not isinstance(details, dict):
                    details = {"raw": str(details)}
                payload[field_name] = details
            else:
                payload[field_name] = str(record.get(field_name, "")).strip()
        return payload

    def _compute_merkle_root(self, leaf_hashes: List[str]) -> str:
        if not leaf_hashes:
            return _GENESIS_HASH

        level = [str(value).strip() for value in leaf_hashes if str(value).strip()]
        if not level:
            return _GENESIS_HASH

        while len(level) > 1:
            if len(level) % 2 == 1:
                level.append(level[-1])
            next_level: List[str] = []
            for index in range(0, len(level), 2):
                combined = f"{level[index]}:{level[index + 1]}"
                digest = hashlib.new(self.hash_algorithm)
                digest.update(combined.encode("utf-8"))
                next_level.append(digest.hexdigest())
            level = next_level
        return level[0]

    @staticmethod
    def _to_csv(records: List[Dict[str, Any]]) -> str:
        if not records:
            header = io.StringIO()
            writer = csv.DictWriter(
                header,
                fieldnames=[
                    "timestamp",
                    "session_id",
                    "event_type",
                    "source_layer",
                    "severity",
                    "details",
                    "previous_hash",
                    "entry_hash",
                    "merkle_root",
                ],
            )
            writer.writeheader()
            return header.getvalue()

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=list(records[0].keys()))
        writer.writeheader()
        for record in records:
            flattened = dict(record)
            flattened["details"] = json.dumps(record.get("details", {}), ensure_ascii=False, sort_keys=True)
            writer.writerow(flattened)
        return output.getvalue()

