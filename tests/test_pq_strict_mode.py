"""Strict production vs lab post-quantum policy enforcement tests."""

from __future__ import annotations

import importlib
import sys
from unittest import mock

import pytest


def _policy_mod():
    return importlib.import_module("src.security.quantum.policy")


@pytest.fixture(autouse=True)
def _reset_policy_cache():
    mod = _policy_mod()
    mod.reset_quantum_policy_cache()
    yield
    mod.reset_quantum_policy_cache()

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from src.security.quantum.hybrid import HybridKeyExchange, _derive_hybrid_secret
from src.security.quantum.kem import QuantumKEM
from src.security.quantum.policy import (
    LAB_FALLBACK_ALGORITHM,
    CryptoMode,
    PostQuantumUnavailableError,
    QuantumSecurityPolicy,
    load_quantum_security_policy,
    reset_quantum_policy_cache,
)
from src.security.quantum.key_storage import (
    FileKeyStorageBackend,
    assert_storage_allowed_for_purpose,
    MISSION_AUTHORITY_PURPOSE,
    KeyStorageError,
)


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


def _prod_policy() -> QuantumSecurityPolicy:
    return QuantumSecurityPolicy(
        crypto_mode=CryptoMode.PRODUCTION,
        kem_fips_name="ML-KEM-768",
        kem_liboqs_name="Kyber768",
        sig_fips_name="ML-DSA-65",
        sig_liboqs_name="Dilithium3",
        hybrid_mode=True,
        keys_dir="configs/keys/quantum",
        key_storage_backend="file",
        cnsa_profile=False,
    )


@pytest.fixture
def mock_oqs_missing():
    """Simulate an environment without liboqs."""
    reset_quantum_policy_cache()
    fake_modules = {k: sys.modules[k] for k in list(sys.modules) if k == "oqs" or k.startswith("oqs.")}
    sys.modules.pop("oqs", None)
    with mock.patch("src.security.quantum.kem._HAS_LIBOQS", False), mock.patch(
        "src.security.quantum.signatures._HAS_LIBOQS", False
    ), mock.patch("src.security.quantum.policy.liboqs_available", return_value=False):
        yield
    sys.modules.update(fake_modules)
    reset_quantum_policy_cache()


class TestProductionStrictMode:
    def test_production_raises_without_liboqs(self, mock_oqs_missing):
        with pytest.raises(PostQuantumUnavailableError):
            QuantumKEM(policy=_prod_policy())

    def test_lab_labels_outputs_when_liboqs_missing(self, mock_oqs_missing):
        kem = QuantumKEM(policy=_lab_policy())
        kp = kem.generate_keypair("lab-kem")
        encap = kem.encapsulate(kp.public_key)
        assert kp.algorithm == LAB_FALLBACK_ALGORITHM
        assert encap.algorithm == LAB_FALLBACK_ALGORITHM


class TestHybridKdf:
    def test_hybrid_kdf_fails_if_either_input_missing(self):
        with pytest.raises(Exception, match="both PQ and classical"):
            _derive_hybrid_secret(b"pq", None, b"transcript")
        with pytest.raises(Exception, match="both PQ and classical"):
            _derive_hybrid_secret(None, b"classical", b"transcript")
        with pytest.raises(Exception, match="both PQ and classical"):
            _derive_hybrid_secret(b"", b"classical", b"transcript")

    def test_hybrid_handshake_requires_classical_keys(self, mock_oqs_missing):
        hkx = HybridKeyExchange(policy=_lab_policy())
        init_sig = hkx.signer.generate_keypair("init")
        resp_kem = hkx.kem.generate_keypair("resp")
        resp_classical = X25519PrivateKey.generate()
        result = hkx.initiate(
            init_sig.secret_key,
            resp_kem.public_key,
            resp_classical.public_key().public_bytes_raw(),
        )
        recovered = hkx.respond(
            result.kem_ciphertext,
            result.classical_public,
            resp_kem.secret_key,
            resp_kem.public_key,
            resp_classical.private_bytes_raw(),
            init_sig.public_key,
            result.signature,
        )
        assert recovered == result.combined_secret


class TestKeyStorageProduction:
    def test_file_backend_rejected_for_mission_authority_in_production(self, tmp_path):
        policy = _prod_policy()
        backend = FileKeyStorageBackend(str(tmp_path))
        with pytest.raises(KeyStorageError, match="mission-authority"):
            assert_storage_allowed_for_purpose(policy, backend, MISSION_AUTHORITY_PURPOSE)

    def test_file_backend_allowed_for_mission_authority_in_lab(self, tmp_path):
        policy = _lab_policy()
        backend = FileKeyStorageBackend(str(tmp_path))
        assert_storage_allowed_for_purpose(policy, backend, MISSION_AUTHORITY_PURPOSE)


class TestFipsAliases:
    def test_config_loader_accepts_legacy_aliases(self, tmp_path, monkeypatch):
        cfg = tmp_path / "q.yaml"
        cfg.write_text(
            "quantum_crypto:\n  crypto_mode: lab\n"
            "  kem_algorithm: Kyber768\n  sig_algorithm: Dilithium3\n"
        )
        monkeypatch.delenv("S3M_CRYPTO_MODE", raising=False)
        reset_quantum_policy_cache()
        pol = load_quantum_security_policy(cfg, reload=True)
        assert pol.kem_fips_name == "ML-KEM-768"
        assert pol.sig_fips_name == "ML-DSA-65"
