"""
Top-level ZKN manager that orchestrates SealedTunnels, XOTC auth,
micro-segmentation, and quantum key lifecycle for the entire S3M stack.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.security.quantum.key_manager import QuantumKeyManager
from src.security.quantum.symmetric import QuantumSymmetricCipher
from src.security.zkn.micro_segmentation import AccessVerdict, MicroSegmentationPolicy
from src.security.zkn.sealed_tunnel import SealedTunnel, TunnelEndpoint
from src.security.zkn.xotc_auth import XOTCAuthenticator


class ZKNManager:
    """Zero Knowledge Networking orchestrator for S3M.

    Lifecycle:
    1. bootstrap() — generate quantum keys for all layers
    2. authenticate() — XOTC credential-less auth per process
    3. open_tunnel() — establish SealedTunnel between layers
    4. send_secure() / receive_secure() — encrypted IPC
    5. rotate_keys() — periodic key rotation
    6. destroy_tunnel() — secure session teardown
    """

    def __init__(
        self, keys_dir: str = "configs/keys/quantum", rotation_hours: int = 24,
    ) -> None:
        self.key_manager = QuantumKeyManager(keys_dir=keys_dir, rotation_hours=rotation_hours)
        self.tunnel = SealedTunnel()
        self.authenticator = XOTCAuthenticator(signer=self.tunnel.signer)
        self.policy = MicroSegmentationPolicy()
        self._endpoints: Dict[str, TunnelEndpoint] = {}
        self._bootstrapped = False

    def bootstrap(self) -> Dict[str, Any]:
        """Initialize quantum keys and register layer endpoints."""
        registry = self.key_manager.bootstrap_all_layers()
        for layer_id in self.key_manager.S3M_LAYERS:
            kem_kp = self.key_manager.get_kem_keypair(layer_id)
            sig_kp = self.key_manager.get_signing_keypair(layer_id)
            self._endpoints[layer_id] = TunnelEndpoint(
                layer_id=layer_id, process_id="*",
                kem_keypair=kem_kp, sig_keypair=sig_kp,
            )
        self._bootstrapped = True
        return {
            "status": "bootstrapped", "layers": len(registry),
            "kem_algorithm": self.tunnel.kem.algorithm,
            "sig_algorithm": self.tunnel.signer.algorithm,
            "registry": registry,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def authenticate_process(self, layer_id: str, process_id: str) -> Dict[str, Any]:
        """Issue XOTC credential-less auth for a process."""
        endpoint = self._endpoints.get(layer_id)
        if not endpoint or not endpoint.sig_keypair:
            raise ValueError(f"Layer {layer_id} not bootstrapped")
        raw_code, record = self.authenticator.issue_code(
            layer_id=layer_id, process_id=process_id,
            signing_secret=endpoint.sig_keypair.secret_key,
        )
        return {
            "code_id": record.code_id, "raw_code": raw_code,
            "layer_id": layer_id, "process_id": process_id,
            "expires_in_seconds": int(record.expires_at - record.issued_at),
        }

    def open_tunnel(
        self, source_layer: str, source_process: str,
        dest_layer: str, dest_process: str,
    ) -> Dict[str, Any]:
        """Open a SealedTunnel after policy check and authentication."""
        verdict = self.policy.evaluate(source_layer, source_process, dest_layer, dest_process)
        if verdict == AccessVerdict.DENY:
            raise PermissionError(
                f"MICRO-SEGMENTATION DENY: {source_layer}/{source_process} "
                f"-> {dest_layer}/{dest_process}"
            )
        initiator = self._endpoints.get(source_layer)
        responder = self._endpoints.get(dest_layer)
        if not initiator or not responder:
            raise ValueError("Source or destination layer not registered")
        initiator.is_initiator = True
        session_id = self.tunnel.establish_tunnel(initiator, responder)
        return {
            "session_id": session_id,
            "source": f"{source_layer}/{source_process}",
            "destination": f"{dest_layer}/{dest_process}",
            "policy_verdict": verdict.value,
            "kem_algorithm": self.tunnel.kem.algorithm,
        }

    def send_secure(self, session_id: str, plaintext: bytes, sender_layer: str) -> Dict[str, Any]:
        endpoint = self._endpoints.get(sender_layer)
        if not endpoint or not endpoint.sig_keypair:
            raise ValueError(f"Sender {sender_layer} not registered")
        return self.tunnel.send(
            session_id=session_id, plaintext=plaintext,
            sender_sig_key=endpoint.sig_keypair.secret_key,
            sender_layer=sender_layer,
        )

    def receive_secure(self, envelope: Dict[str, Any], sender_layer: str) -> bytes:
        endpoint = self._endpoints.get(sender_layer)
        if not endpoint or not endpoint.sig_keypair:
            raise ValueError(f"Sender {sender_layer} not registered")
        return self.tunnel.receive(envelope, endpoint.sig_keypair.public_key)

    def rotate_all_keys(self) -> List[Dict[str, str]]:
        results = self.key_manager.rotate_all()
        for layer_id in self.key_manager.S3M_LAYERS:
            kem_kp = self.key_manager.get_kem_keypair(layer_id)
            sig_kp = self.key_manager.get_signing_keypair(layer_id)
            if layer_id in self._endpoints:
                self._endpoints[layer_id].kem_keypair = kem_kp
                self._endpoints[layer_id].sig_keypair = sig_kp
        return results

    def get_status(self) -> Dict[str, Any]:
        return {
            "bootstrapped": self._bootstrapped,
            "layers_registered": len(self._endpoints),
            "active_tunnels": len(self.tunnel.get_active_sessions()),
            "policy_rules": len(self.policy.list_rules()),
            "kem_algorithm": self.tunnel.kem.algorithm,
            "sig_algorithm": self.tunnel.signer.algorithm,
        }
