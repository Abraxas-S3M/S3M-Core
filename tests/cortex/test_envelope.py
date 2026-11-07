"""Cortex envelope uses the same strict quantum policy loader as S3M QSS."""

from __future__ import annotations

import pytest

from src.cortex.envelope import CortexEnvelopeCodec
from src.security.quantum.kem import QuantumKEM
from src.security.quantum.policy import CryptoMode, QuantumSecurityPolicy
from src.security.quantum.signatures import QuantumSigner


def _lab_policy() -> QuantumSecurityPolicy:
    return QuantumSecurityPolicy(
        crypto_mode=CryptoMode.LAB,
        kem_fips_name="ML-KEM-768",
        kem_liboqs_name="Kyber768",
        sig_fips_name="ML-DSA-65",
        sig_liboqs_name="Dilithium3",
        hybrid_mode=True,
        keys_dir="configs/keys/quantum",
        key_storage_backend="file",
        cnsa_profile=False,
    )


def test_cortex_codec_shares_policy_with_qss():
    policy = _lab_policy()
    codec = CortexEnvelopeCodec(policy=policy)
    kem = QuantumKEM(policy=policy)
    signer = QuantumSigner(policy=policy)
    recipient = kem.generate_keypair("cortex-recv")
    signing = signer.generate_keypair("cortex-sign")
    env = codec.seal(b"observable-ioc", recipient.public_key, signing.secret_key)
    summary = codec.policy_summary()
    assert summary["crypto_mode"] == "lab"
    assert summary["kem_algorithm"] == "ML-KEM-768"
    assert env.kem_algorithm  # sealed under active KEM policy
