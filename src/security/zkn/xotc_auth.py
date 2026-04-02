"""
Xiid One-Time Code (XOTC) authentication — credential-less access.

No passwords, no shared keys, no certificates transmitted over the wire.
Each authentication attempt uses a single-use, time-bound, quantum-signed code.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.security.quantum.signatures import QuantumSigner


@dataclass
class OneTimeCode:
    """Single-use authentication token."""
    code_id: str
    code_hash: str
    layer_id: str
    process_id: str
    issued_at: float
    expires_at: float
    used: bool = False
    signature: bytes = b""


class XOTCAuthenticator:
    """Zero-knowledge, credential-less authentication for S3M processes.

    Protocol:
    1. Process requests auth -> Authenticator generates a one-time code
    2. Code is transmitted via SealedTunnel to the process
    3. Process presents code_hash + signature to prove identity
    4. Code is immediately invalidated after single use
    """

    DEFAULT_TTL_SECONDS = 30

    def __init__(self, signer: Optional[QuantumSigner] = None) -> None:
        self.signer = signer or QuantumSigner()
        self._issued_codes: Dict[str, OneTimeCode] = {}
        self._used_codes: List[str] = []

    def issue_code(
        self, layer_id: str, process_id: str,
        signing_secret: bytes, ttl: int = DEFAULT_TTL_SECONDS,
    ) -> Tuple[str, OneTimeCode]:
        """Issue a one-time authentication code.
        Returns (raw_code, code_record). raw_code is NOT stored."""
        raw_code = secrets.token_hex(32)
        code_hash = hashlib.sha256(raw_code.encode()).hexdigest()
        code_id = f"xotc-{secrets.token_hex(8)}"
        now = time.time()

        sig_data = f"{code_id}|{code_hash}|{layer_id}|{process_id}".encode()
        signature = self.signer.sign(sig_data, signing_secret)

        record = OneTimeCode(
            code_id=code_id, code_hash=code_hash,
            layer_id=layer_id, process_id=process_id,
            issued_at=now, expires_at=now + ttl, signature=signature,
        )
        self._issued_codes[code_id] = record
        return raw_code, record

    def verify_code(
        self, code_id: str, presented_code: str, signing_public: bytes,
    ) -> bool:
        """Verify a one-time code. Single-use: invalidated after verification."""
        record = self._issued_codes.get(code_id)
        if not record:
            return False
        if time.time() > record.expires_at:
            self._invalidate(code_id)
            return False
        if record.used:
            return False

        presented_hash = hashlib.sha256(presented_code.encode()).hexdigest()
        if presented_hash != record.code_hash:
            return False

        sig_data = f"{code_id}|{record.code_hash}|{record.layer_id}|{record.process_id}".encode()
        if not self.signer.verify(sig_data, record.signature, signing_public):
            return False

        self._invalidate(code_id)
        return True

    def _invalidate(self, code_id: str) -> None:
        record = self._issued_codes.pop(code_id, None)
        if record:
            record.used = True
            self._used_codes.append(code_id)

    def cleanup_expired(self) -> int:
        now = time.time()
        expired = [cid for cid, rec in self._issued_codes.items() if now > rec.expires_at]
        for cid in expired:
            self._invalidate(cid)
        return len(expired)
