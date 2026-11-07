"""Ed25519 signing helpers for mock signed_record_ref payloads."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


@dataclass(slots=True)
class RecordSigner:
    """Signs tactical change records for mock rollback/evidence drills."""

    _private_key: Ed25519PrivateKey

    @classmethod
    def generate(cls) -> "RecordSigner":
        return cls(_private_key=Ed25519PrivateKey.generate())

    @property
    def public_key_b64(self) -> str:
        raw = self._private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return base64.urlsafe_b64encode(raw).decode("ascii")

    def sign_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        signature = self._private_key.sign(canonical)
        return {
            "record_digest": digest,
            "signature_b64": base64.urlsafe_b64encode(signature).decode("ascii"),
            "signer_public_key_b64": self.public_key_b64,
        }

    def verify_record(self, record: Dict[str, Any], signature_b64: str) -> bool:
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        try:
            signature = base64.urlsafe_b64decode(signature_b64.encode("ascii"))
            self._private_key.public_key().verify(signature, canonical)
            return True
        except Exception:
            return False
