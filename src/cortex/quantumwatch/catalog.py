"""QuantumWatch algorithm catalogue: what each primitive is and how quantum affects it.

Military/tactical context:
Every discovered algorithm is normalised to one canonical id and classified once, so the
inventory, the risk model and the CBOM agree on what "vulnerable" means.

Quantum status:
- ``broken_by_shor``: public-key schemes a CRQC breaks (RSA, finite-field and elliptic-curve
  DH, ECDSA, EdDSA). Confidentiality uses are exposed to harvest-now-decrypt-later.
- ``grover_reduced``: symmetric primitives whose margin halves; acceptable at >= 128-bit
  (NIST) or only at 256-bit (CNSA 2.0).
- ``pq``: post-quantum standards (FIPS 203/204/205, SP 800-208).
- ``hybrid``: classical + PQ combination; resilient if either part holds.
- ``classically_broken``: already unsafe without a quantum computer (MD5, SHA-1, RC4, DES).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class Algo:
    algo_id: str
    family: str
    primitive: str  # kem | key-agree | signature | block-cipher | ae | hash | mac | kdf | protocol
    quantum: str  # broken_by_shor | grover_reduced | pq | hybrid | classically_broken | n/a
    bits: Optional[int] = None  # classical security bits / key bits for symmetric
    nist_category: Optional[int] = None  # PQ security category (1, 3, 5)
    profile_name: Optional[str] = None  # name used by profiles (e.g. ML-KEM-768, SHA-256)


_A = Algo
CATALOG: Dict[str, Algo] = {a.algo_id: a for a in [
    _A("rsa-2048", "RSA", "signature", "broken_by_shor", 112),
    _A("rsa-3072", "RSA", "signature", "broken_by_shor", 128),
    _A("rsa-4096", "RSA", "signature", "broken_by_shor", 152),
    _A("rsa-kex", "RSA", "key-agree", "broken_by_shor", 112),
    _A("ecdh-p256", "ECDH", "key-agree", "broken_by_shor", 128),
    _A("ecdh-p384", "ECDH", "key-agree", "broken_by_shor", 192),
    _A("x25519", "ECDH", "key-agree", "broken_by_shor", 128),
    _A("dh-ffdhe", "DH", "key-agree", "broken_by_shor", 112),
    _A("ecdsa-p256", "ECDSA", "signature", "broken_by_shor", 128),
    _A("ecdsa-p384", "ECDSA", "signature", "broken_by_shor", 192),
    _A("ed25519", "EdDSA", "signature", "broken_by_shor", 128),
    _A("ml-kem-512", "ML-KEM", "kem", "pq", nist_category=1, profile_name="ML-KEM-512"),
    _A("ml-kem-768", "ML-KEM", "kem", "pq", nist_category=3, profile_name="ML-KEM-768"),
    _A("ml-kem-1024", "ML-KEM", "kem", "pq", nist_category=5, profile_name="ML-KEM-1024"),
    _A("ml-dsa-44", "ML-DSA", "signature", "pq", nist_category=2, profile_name="ML-DSA-44"),
    _A("ml-dsa-65", "ML-DSA", "signature", "pq", nist_category=3, profile_name="ML-DSA-65"),
    _A("ml-dsa-87", "ML-DSA", "signature", "pq", nist_category=5, profile_name="ML-DSA-87"),
    _A("ml-kem", "ML-KEM", "kem", "pq"),  # parameter set not determinable statically
    _A("ml-dsa", "ML-DSA", "signature", "pq"),
    _A("slh-dsa", "SLH-DSA", "signature", "pq", nist_category=1, profile_name="SLH-DSA"),
    _A("lms", "LMS", "signature", "pq", profile_name="LMS"),
    _A("x25519-ml-kem-768", "hybrid", "kem", "hybrid", nist_category=3, profile_name="ML-KEM-768"),
    _A("p384-ml-kem-1024", "hybrid", "kem", "hybrid", nist_category=5, profile_name="ML-KEM-1024"),
    _A("aes-128", "AES", "block-cipher", "grover_reduced", 128),
    _A("aes-256", "AES", "block-cipher", "grover_reduced", 256),
    _A("aes-128-gcm", "AES", "ae", "grover_reduced", 128),
    _A("aes-256-gcm", "AES", "ae", "grover_reduced", 256),
    _A("aes-128-cbc-hmac", "AES", "ae", "grover_reduced", 128),
    _A("chacha20-poly1305", "ChaCha20", "ae", "grover_reduced", 256),
    _A("sha-256", "SHA-2", "hash", "grover_reduced", 256, profile_name="SHA-256"),
    _A("sha-384", "SHA-2", "hash", "grover_reduced", 384, profile_name="SHA-384"),
    _A("sha-512", "SHA-2", "hash", "grover_reduced", 512, profile_name="SHA-512"),
    _A("sha3-256", "SHA-3", "hash", "grover_reduced", 256, profile_name="SHA3-256"),
    _A("hmac-sha256", "HMAC", "mac", "grover_reduced", 256),
    _A("pbkdf2-sha256", "PBKDF2", "kdf", "grover_reduced", 256),
    _A("hkdf-sha256", "HKDF", "kdf", "grover_reduced", 256),
    _A("scrypt", "scrypt", "kdf", "grover_reduced", 256),
    _A("md5", "MD5", "hash", "classically_broken", 0),
    _A("sha-1", "SHA-1", "hash", "classically_broken", 63),
    _A("rc4", "RC4", "ae", "classically_broken", 0),
    _A("3des", "3DES", "block-cipher", "classically_broken", 112),
    _A("cleartext", "none", "protocol", "classically_broken", 0),
    _A("xiid-sealedtunnel", "XiiD", "protocol", "hybrid"),  # vendor claim: REQUIRES XIID VALIDATION
    _A("unknown", "unknown", "protocol", "n/a"),
]}


def get(algo_id: str) -> Algo:
    return CATALOG.get(algo_id, CATALOG["unknown"])


def approved(algo: Algo, profile: Dict) -> bool:
    """Is this algorithm acceptable under a quantum-resilient profile (ignoring dates)?"""
    if algo.quantum in ("broken_by_shor", "classically_broken", "n/a"):
        return False
    if algo.quantum == "hybrid":
        if algo.algo_id == "xiid-sealedtunnel":
            return False  # cannot be approved until XiiD documents the profile
        return bool(profile.get("hybrid_accepted")) and algo.profile_name in profile.get("kem", [])
    if algo.quantum == "pq":
        return algo.profile_name in (profile.get("kem", []) + profile.get("signature", []))
    if algo.primitive == "hash":
        return algo.profile_name in profile.get("hash", [])
    return (algo.bits or 0) >= int(profile.get("symmetric_min_bits", 128))


__all__ = ["Algo", "CATALOG", "approved", "get"]
