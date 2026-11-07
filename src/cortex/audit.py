"""Merkle audit bridge for Cortex pipeline stages with ML-DSA hourly checkpoints.

Military/tactical context: forward operators must prove the decision chain was not
altered after the fact; hourly signed checkpoints anchor manifest digests from the
strict model loader (Prompt 4 contract).
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from s3m_core.defense.audit.merkle_log import AuditEntry, IntegrityReport, MerkleAuditLog
from src.cortex.scrubber import scrub_mapping
from src.edge_runtime.model_manifest import ModelManifest
from src.security.quantum.signatures import QuantumSigner, SigningKeyPair


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _manifest_digests(manifest_dir: str | Path) -> Dict[str, str]:
    """SHA-256 digests of each strict manifest file (Prompt 4 loader inputs)."""
    root = Path(manifest_dir)
    if not root.is_dir():
        return {}
    digests: Dict[str, str] = {}
    for manifest in sorted(root.glob("*.y*ml")):
        try:
            ModelManifest._from_file(manifest)  # strict parse — invalid files raise/skip
        except Exception:
            continue
        digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        digests[manifest.stem] = digest
    return digests


@dataclass(frozen=True, slots=True)
class SignedCheckpoint:
    hour_bucket: str
    merkle_root: str
    manifest_digests: Dict[str, str]
    algorithm: str
    key_id: str
    signature_b64: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hour_bucket": self.hour_bucket,
            "merkle_root": self.merkle_root,
            "manifest_digests": dict(self.manifest_digests),
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "signature_b64": self.signature_b64,
        }


class CortexAuditRecorder:
    """Append Cortex stage records and emit hourly ML-DSA signed checkpoints."""

    def __init__(
        self,
        *,
        log_path: str | Path,
        signer: Optional[QuantumSigner] = None,
        signing_key: Optional[SigningKeyPair] = None,
        manifest_dir: str | Path = "configs/model_manifests",
    ) -> None:
        self._log = MerkleAuditLog(str(log_path))
        self._signer = signer or QuantumSigner()
        self._signing_key = signing_key or self._signer.generate_keypair("cortex-audit")
        self._manifest_dir = Path(manifest_dir)
        self._last_checkpoint_hour: Optional[datetime] = None

    @property
    def log_path(self) -> Path:
        return self._log.log_path

    def record_stage(
        self,
        *,
        case_id: str,
        stage: str,
        event_type: str,
        details: Dict[str, Any],
        severity: str = "info",
    ) -> str:
        """Write one scrubbed pipeline stage into the Merkle audit log."""
        now = _utc_now()
        entry = AuditEntry(
            timestamp=now,
            session_id=str(case_id),
            event_type=event_type,
            source_layer=f"cortex.{stage}",
            severity=severity,
            details=scrub_mapping(details),
            previous_hash="",
        )
        entry_hash = self._log.append(entry)
        self._maybe_emit_checkpoint(now)
        return entry_hash

    def verify_integrity(self) -> IntegrityReport:
        return self._log.verify_integrity()

    def export_case_records(self, case_id: str) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        if not self.log_path.is_file():
            return records
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if str(record.get("session_id", "")) == str(case_id):
                    records.append(record)
        return records

    def verify_checkpoints(self) -> bool:
        """Validate ML-DSA signatures on checkpoint records."""
        public_key = self._signing_key.public_key
        for record in self._iter_checkpoint_records():
            details = record.get("details") or {}
            if not isinstance(details, dict):
                return False
            payload = self._checkpoint_payload(details)
            signature = base64.b64decode(str(details.get("signature_b64", "")))
            if not self._signer.verify(payload, signature, public_key):
                return False
        return True

    def _maybe_emit_checkpoint(self, moment: datetime) -> None:
        hour_bucket = moment.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        if self._last_checkpoint_hour == hour_bucket:
            return
        merkle_root = self._latest_merkle_root()
        if not merkle_root:
            return
        manifest_digests = _manifest_digests(self._manifest_dir)
        checkpoint_body = {
            "hour_bucket": hour_bucket.isoformat(),
            "merkle_root": merkle_root,
            "manifest_digests": manifest_digests,
            "signer_key_id": self._signing_key.key_id,
            "signer_algorithm": self._signing_key.algorithm,
        }
        payload = self._checkpoint_payload(checkpoint_body)
        signature = self._signer.sign(payload, self._signing_key.secret_key)
        signed = SignedCheckpoint(
            hour_bucket=hour_bucket.isoformat(),
            merkle_root=merkle_root,
            manifest_digests=manifest_digests,
            algorithm=self._signing_key.algorithm,
            key_id=self._signing_key.key_id,
            signature_b64=base64.b64encode(signature).decode("ascii"),
        )
        entry = AuditEntry(
            timestamp=moment,
            session_id="cortex-checkpoint",
            event_type="cortex.audit_checkpoint",
            source_layer="cortex.audit",
            severity="audit",
            details=signed.to_dict(),
            previous_hash="",
        )
        self._log.append(entry)
        self._last_checkpoint_hour = hour_bucket

    def _latest_merkle_root(self) -> str:
        if not self.log_path.is_file():
            return ""
        last_root = ""
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                root = str(record.get("merkle_root", "")).strip()
                if root:
                    last_root = root
        return last_root

    def _iter_checkpoint_records(self) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        if not self.log_path.is_file():
            return records
        with self.log_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if str(record.get("event_type", "")) == "cortex.audit_checkpoint":
                    records.append(record)
        return records

    @staticmethod
    def _checkpoint_payload(details: Dict[str, Any]) -> bytes:
        canonical = json.dumps(
            {
                "hour_bucket": details.get("hour_bucket"),
                "merkle_root": details.get("merkle_root"),
                "manifest_digests": details.get("manifest_digests"),
                "signer_algorithm": details.get("signer_algorithm") or details.get("algorithm"),
                "signer_key_id": details.get("signer_key_id") or details.get("key_id"),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return canonical.encode("utf-8")
