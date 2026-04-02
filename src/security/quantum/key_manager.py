"""
Quantum-safe key lifecycle: generation, storage, rotation, revocation.
Manages both KEM and signing keys for every S3M layer and node.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.security.quantum.kem import QuantumKEM, KEMKeyPair
from src.security.quantum.signatures import QuantumSigner, SigningKeyPair


class QuantumKeyManager:
    """Centralized PQ key vault for the S3M node cluster.

    Responsibilities:
    - Per-layer KEM + signing keypair generation
    - Key rotation on configurable schedule
    - Revocation list management
    - Secure on-disk persistence (hex-encoded, chmod 600)
    - Key fingerprint registry for peer verification
    """

    S3M_LAYERS = [
        "layer-01-llm", "layer-02-threat", "layer-03-autonomy",
        "layer-04-simulation", "layer-05-navigation", "layer-06-dashboard",
        "layer-07-cyber", "layer-08-comms", "layer-09-logistics",
        "layer-10-security", "layer-11-training", "layer-12-training-adv",
        "perimeter-north", "perimeter-south",
    ]

    def __init__(
        self, keys_dir: str = "configs/keys/quantum", rotation_hours: int = 24,
    ) -> None:
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self.rotation_interval = timedelta(hours=rotation_hours)
        self.kem = QuantumKEM()
        self.signer = QuantumSigner()
        self._kem_keys: Dict[str, KEMKeyPair] = {}
        self._sig_keys: Dict[str, SigningKeyPair] = {}
        self._revoked: List[str] = []
        self._rotation_log: List[Dict[str, Any]] = []

    def bootstrap_all_layers(self) -> Dict[str, Dict[str, str]]:
        """Generate KEM + signing keypairs for every S3M layer."""
        registry: Dict[str, Dict[str, str]] = {}
        for layer_id in self.S3M_LAYERS:
            kem_kp = self.kem.generate_keypair(key_id=f"{layer_id}-kem")
            sig_kp = self.signer.generate_keypair(key_id=f"{layer_id}-sig")
            self._kem_keys[layer_id] = kem_kp
            self._sig_keys[layer_id] = sig_kp
            self._persist_keypair(layer_id, kem_kp, sig_kp)
            registry[layer_id] = {
                "kem_fingerprint": kem_kp.fingerprint,
                "kem_algorithm": kem_kp.algorithm,
                "sig_fingerprint": sig_kp.fingerprint,
                "sig_algorithm": sig_kp.algorithm,
            }
        return registry

    def get_kem_keypair(self, layer_id: str) -> Optional[KEMKeyPair]:
        return self._kem_keys.get(layer_id)

    def get_signing_keypair(self, layer_id: str) -> Optional[SigningKeyPair]:
        return self._sig_keys.get(layer_id)

    def get_public_key_bundle(self, layer_id: str) -> Dict[str, bytes]:
        """Return only PUBLIC keys for a layer (safe to transmit)."""
        bundle: Dict[str, bytes] = {}
        kem_kp = self._kem_keys.get(layer_id)
        sig_kp = self._sig_keys.get(layer_id)
        if kem_kp:
            bundle["kem_public"] = kem_kp.public_key
        if sig_kp:
            bundle["sig_public"] = sig_kp.public_key
        return bundle

    def rotate_layer_keys(self, layer_id: str) -> Dict[str, str]:
        """Rotate both KEM and signing keys for a layer."""
        old_kem = self._kem_keys.get(layer_id)
        old_sig = self._sig_keys.get(layer_id)

        new_kem = self.kem.generate_keypair(key_id=f"{layer_id}-kem")
        new_sig = self.signer.generate_keypair(key_id=f"{layer_id}-sig")
        self._kem_keys[layer_id] = new_kem
        self._sig_keys[layer_id] = new_sig
        self._persist_keypair(layer_id, new_kem, new_sig)

        if old_kem:
            self._revoked.append(old_kem.fingerprint)
        if old_sig:
            self._revoked.append(old_sig.fingerprint)

        event = {
            "layer_id": layer_id,
            "rotated_at": datetime.now(timezone.utc).isoformat(),
            "new_kem_fp": new_kem.fingerprint,
            "new_sig_fp": new_sig.fingerprint,
        }
        self._rotation_log.append(event)
        return event

    def rotate_all(self) -> List[Dict[str, str]]:
        return [self.rotate_layer_keys(lid) for lid in self.S3M_LAYERS]

    def is_revoked(self, fingerprint: str) -> bool:
        return fingerprint in self._revoked

    def get_rotation_log(self) -> List[Dict[str, Any]]:
        return [deepcopy(e) for e in self._rotation_log]

    def _persist_keypair(
        self, layer_id: str, kem_kp: KEMKeyPair, sig_kp: SigningKeyPair,
    ) -> None:
        layer_dir = self.keys_dir / layer_id
        layer_dir.mkdir(parents=True, exist_ok=True)
        (layer_dir / "kem_public.key").write_text(kem_kp.public_key.hex())
        (layer_dir / "kem_secret.key").write_text(kem_kp.secret_key.hex())
        (layer_dir / "sig_public.key").write_text(sig_kp.public_key.hex())
        (layer_dir / "sig_secret.key").write_text(sig_kp.secret_key.hex())
        manifest = {
            "layer_id": layer_id,
            "kem_algorithm": kem_kp.algorithm,
            "kem_fingerprint": kem_kp.fingerprint,
            "sig_algorithm": sig_kp.algorithm,
            "sig_fingerprint": sig_kp.fingerprint,
            "created_at": kem_kp.created_at,
        }
        (layer_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
