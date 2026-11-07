"""
Quantum Security policy loader — single source of truth for S3M and Cortex.

Tactical context: deployed nodes must not silently operate without NIST PQC
when mission policy declares production crypto; lab fallbacks are allowed only
in development ranges and must be visibly labeled.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)

LAB_FALLBACK_ALGORITHM = "LAB-FALLBACK-NOT-PQ"

DEFAULT_CONFIG_PATH = Path("configs/quantum_security.yaml")


class CryptoMode(str, Enum):
    """Operational crypto posture for the node cluster."""

    PRODUCTION = "production"
    LAB = "lab"


class PostQuantumUnavailableError(RuntimeError):
    """Raised when production policy requires liboqs but it is not installed."""


# FIPS-facing names -> liboqs mechanism names
KEM_ALIASES: Dict[str, str] = {
    "ML-KEM-768": "Kyber768",
    "ML-KEM-1024": "Kyber1024",
    "Kyber768": "Kyber768",
    "Kyber-768": "Kyber768",
    "Kyber1024": "Kyber1024",
    "Kyber-1024": "Kyber1024",
}

SIG_ALIASES: Dict[str, str] = {
    "ML-DSA-65": "Dilithium3",
    "ML-DSA-87": "Dilithium5",
    "Dilithium3": "Dilithium3",
    "Dilithium-3": "Dilithium3",
    "Dilithium5": "Dilithium5",
    "Dilithium-5": "Dilithium5",
}

FIPS_KEM_NAME: Dict[str, str] = {
    "Kyber768": "ML-KEM-768",
    "Kyber1024": "ML-KEM-1024",
}

FIPS_SIG_NAME: Dict[str, str] = {
    "Dilithium3": "ML-DSA-65",
    "Dilithium5": "ML-DSA-87",
}

CNSA_KEM = "ML-KEM-1024"
CNSA_SIG = "ML-DSA-87"


@dataclass(frozen=True)
class QuantumSecurityPolicy:
    """Loaded quantum crypto policy from configuration."""

    crypto_mode: CryptoMode
    kem_fips_name: str
    kem_liboqs_name: str
    sig_fips_name: str
    sig_liboqs_name: str
    hybrid_mode: bool
    keys_dir: str
    key_storage_backend: str
    cnsa_profile: bool

    @property
    def is_production(self) -> bool:
        return self.crypto_mode == CryptoMode.PRODUCTION

    @property
    def is_lab(self) -> bool:
        return self.crypto_mode == CryptoMode.LAB


def resolve_kem_algorithm(name: str) -> Tuple[str, str]:
    """Return (FIPS display name, liboqs mechanism name) for a configured KEM."""
    key = name.strip()
    if key not in KEM_ALIASES:
        raise ValueError(f"Unknown KEM algorithm: {name!r}")
    liboqs_name = KEM_ALIASES[key]
    fips = FIPS_KEM_NAME[liboqs_name]
    return fips, liboqs_name


def resolve_sig_algorithm(name: str) -> Tuple[str, str]:
    """Return (FIPS display name, liboqs mechanism name) for a configured sig."""
    key = name.strip()
    if key not in SIG_ALIASES:
        raise ValueError(f"Unknown signature algorithm: {name!r}")
    liboqs_name = SIG_ALIASES[key]
    fips = FIPS_SIG_NAME[liboqs_name]
    return fips, liboqs_name


def load_quantum_security_policy(
    config_path: Optional[Path | str] = None,
    *,
    reload: bool = False,
) -> QuantumSecurityPolicy:
    """Load and validate quantum security policy from YAML (+ env overrides)."""
    global _CACHED_POLICY
    if not reload and _CACHED_POLICY is not None:
        return _CACHED_POLICY

    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    raw: Dict[str, Any] = {}
    if path.is_file():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    qc: Dict[str, Any] = raw.get("quantum_crypto") or {}

    mode_str = os.environ.get("S3M_CRYPTO_MODE", qc.get("crypto_mode", "production"))
    try:
        crypto_mode = CryptoMode(mode_str.lower())
    except ValueError as exc:
        raise ValueError(f"Invalid crypto_mode: {mode_str!r}") from exc

    cnsa = bool(qc.get("cnsa_profile", False))
    kem_cfg = qc.get("kem_algorithm", CNSA_KEM if cnsa else "ML-KEM-768")
    sig_cfg = qc.get("sig_algorithm", CNSA_SIG if cnsa else "ML-DSA-65")
    kem_fips, kem_liboqs = resolve_kem_algorithm(str(kem_cfg))
    sig_fips, sig_liboqs = resolve_sig_algorithm(str(sig_cfg))

    policy = QuantumSecurityPolicy(
        crypto_mode=crypto_mode,
        kem_fips_name=kem_fips,
        kem_liboqs_name=kem_liboqs,
        sig_fips_name=sig_fips,
        sig_liboqs_name=sig_liboqs,
        hybrid_mode=bool(qc.get("hybrid_mode", True)),
        keys_dir=str(qc.get("keys_dir", "configs/keys/quantum")),
        key_storage_backend=str(qc.get("key_storage_backend", "file")),
        cnsa_profile=cnsa,
    )
    _CACHED_POLICY = policy
    return policy


def reset_quantum_policy_cache() -> None:
    """Clear cached policy (unit tests)."""
    global _CACHED_POLICY
    _CACHED_POLICY = None


def liboqs_available() -> bool:
    try:
        import oqs  # noqa: F401

        return True
    except ImportError:
        return False


def enforce_pq_availability(policy: QuantumSecurityPolicy) -> None:
    """Fail closed in production when liboqs is absent."""
    if policy.is_production and not liboqs_available():
        raise PostQuantumUnavailableError(
            "Production crypto_mode requires liboqs (ML-KEM / ML-DSA); "
            "install oqs-python or set crypto_mode: lab for development only."
        )


def log_lab_fallback(component: str) -> None:
    """Emit a visible warning when non-PQ fallback is engaged."""
    logger.warning(
        "%s: liboqs unavailable — using LAB fallback (%s); NOT suitable for deployment",
        component,
        LAB_FALLBACK_ALGORITHM,
    )


_CACHED_POLICY: Optional[QuantumSecurityPolicy] = None
