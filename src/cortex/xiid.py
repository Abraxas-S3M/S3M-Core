"""XiiD signed record references for Cortex brokered actions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from src.security.quantum.signatures import QuantumSigner, SigningKeyPair


@dataclass(frozen=True, slots=True)
class XiiDRecordRef:
    record_id: str
    uri: str
    algorithm: str
    signature_b64: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "uri": self.uri,
            "algorithm": self.algorithm,
            "signature_b64": self.signature_b64,
        }


class XiiDRecorder:
    """Mint offline signed references to XiiD call records."""

    def __init__(
        self,
        *,
        signer: QuantumSigner | None = None,
        signing_key: SigningKeyPair | None = None,
    ) -> None:
        self._signer = signer or QuantumSigner()
        self._signing_key = signing_key or self._signer.generate_keypair("xiid-cortex")

    def record_call(
        self,
        *,
        case_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        observed_result: Dict[str, Any],
    ) -> XiiDRecordRef:
        timestamp = datetime.now(timezone.utc).isoformat()
        body = {
            "case_id": case_id,
            "tool_name": tool_name,
            "parameters": parameters,
            "observed_result": observed_result,
            "timestamp": timestamp,
        }
        canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        signature = self._signer.sign(canonical.encode("utf-8"), self._signing_key.secret_key)
        import base64

        return XiiDRecordRef(
            record_id=digest[:16],
            uri=f"xiid://record/{digest}",
            algorithm=self._signing_key.algorithm,
            signature_b64=base64.b64encode(signature).decode("ascii"),
        )
