"""
SealedTunnel-style triple-encrypted process-to-process channel.

Encryption layers (inside-out):
  INNER:  AES-256-GCM with quantum-derived session key (payload)
  MIDDLE: Post-quantum KEM envelope (session key transport)
  OUTER:  TLS 1.3 / mTLS wrapper (transport, handled by OS)

This module handles the INNER + MIDDLE layers.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.security.quantum.kem import QuantumKEM, KEMKeyPair
from src.security.quantum.signatures import QuantumSigner, SigningKeyPair
from src.security.quantum.symmetric import QuantumSymmetricCipher, SealedPayload


@dataclass
class TunnelEndpoint:
    """Represents one side of a SealedTunnel."""
    layer_id: str
    process_id: str
    kem_keypair: Optional[KEMKeyPair] = None
    sig_keypair: Optional[SigningKeyPair] = None
    is_initiator: bool = False


@dataclass
class TunnelSession:
    """Active encrypted session between two endpoints."""
    session_id: str
    initiator: str
    responder: str
    session_key: bytes
    created_at: float
    message_count: int = 0
    max_messages: int = 10000
    ttl_seconds: int = 3600


class SealedTunnel:
    """Triple-encrypted, outbound-only, process-to-process channel.

    Design principles from Xiid ZKN:
    - No inbound ports opened on any S3M layer process
    - All connections are outbound-initiated
    - Session keys are ephemeral and quantum-derived
    - Every payload is signed for integrity + non-repudiation
    - Anti-replay via monotonic sequence counters
    """

    def __init__(self) -> None:
        self.kem = QuantumKEM()
        self.signer = QuantumSigner()
        self.cipher = QuantumSymmetricCipher()
        self._sessions: Dict[str, TunnelSession] = {}
        self._message_log: List[Dict[str, Any]] = []

    def establish_tunnel(
        self, initiator: TunnelEndpoint, responder: TunnelEndpoint,
    ) -> str:
        """Perform quantum key exchange and establish encrypted tunnel."""
        if not responder.kem_keypair or not initiator.sig_keypair:
            raise ValueError("Both endpoints must have quantum keys provisioned")

        encap = self.kem.encapsulate(responder.kem_keypair.public_key)

        session_key = self.cipher.derive_session_key(
            encap.shared_secret,
            context=f"S3M-ST-{initiator.layer_id}-{responder.layer_id}".encode(),
        )

        session_id = f"st-{secrets.token_hex(12)}"
        session = TunnelSession(
            session_id=session_id, initiator=initiator.layer_id,
            responder=responder.layer_id, session_key=session_key,
            created_at=time.time(),
        )
        self._sessions[session_id] = session

        self._message_log.append({
            "event": "tunnel_established", "session_id": session_id,
            "initiator": initiator.layer_id, "responder": responder.layer_id,
            "kem_algorithm": self.kem.algorithm,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        return session_id

    def send(
        self, session_id: str, plaintext: bytes,
        sender_sig_key: bytes, sender_layer: str,
    ) -> Dict[str, Any]:
        """Encrypt, sign, and package a payload through the tunnel."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"No active tunnel session: {session_id}")
        if session.message_count >= session.max_messages:
            raise ValueError(f"Session {session_id} exceeded max messages — rekey required")
        elapsed = time.time() - session.created_at
        if elapsed > session.ttl_seconds:
            raise ValueError(f"Session {session_id} TTL expired — rekey required")

        sealed = self.cipher.encrypt(
            plaintext=plaintext, session_key=session.session_key,
            layer_tag=sender_layer,
        )

        sig_payload = sealed.nonce + sealed.ciphertext + sealed.aad
        signature = self.signer.sign(sig_payload, sender_sig_key)
        session.message_count += 1

        return {
            "session_id": session_id,
            "nonce": sealed.nonce.hex(),
            "ciphertext": sealed.ciphertext.hex(),
            "aad": sealed.aad.hex(),
            "signature": signature.hex(),
            "sequence": sealed.sequence,
            "layer_tag": sealed.layer_tag,
        }

    def receive(
        self, envelope: Dict[str, Any], sender_sig_public: bytes,
    ) -> bytes:
        """Verify signature and decrypt a tunneled payload."""
        session_id = envelope["session_id"]
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"No active tunnel session: {session_id}")

        nonce = bytes.fromhex(envelope["nonce"])
        ciphertext = bytes.fromhex(envelope["ciphertext"])
        aad = bytes.fromhex(envelope["aad"])
        signature = bytes.fromhex(envelope["signature"])

        sig_payload = nonce + ciphertext + aad
        if not self.signer.verify(sig_payload, signature, sender_sig_public):
            raise ValueError("SEALED TUNNEL BREACH: Invalid signature — payload rejected")

        sealed = SealedPayload(
            nonce=nonce, ciphertext=ciphertext, aad=aad,
            layer_tag=envelope.get("layer_tag", "unknown"),
            sequence=envelope.get("sequence", 0),
        )
        return self.cipher.decrypt(sealed, session.session_key)

    def destroy_tunnel(self, session_id: str) -> bool:
        """Securely destroy a tunnel session (zeroize keys)."""
        session = self._sessions.pop(session_id, None)
        if session:
            session.session_key = secrets.token_bytes(32)
            self._message_log.append({
                "event": "tunnel_destroyed", "session_id": session_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return True
        return False

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        return [
            {
                "session_id": s.session_id, "initiator": s.initiator,
                "responder": s.responder, "message_count": s.message_count,
                "age_seconds": int(time.time() - s.created_at),
            }
            for s in self._sessions.values()
        ]
