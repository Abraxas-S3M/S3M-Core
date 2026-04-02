"""Integration tests for the S3M Quantum Security Shell."""

import pytest
from src.security.quantum.kem import QuantumKEM
from src.security.quantum.signatures import QuantumSigner
from src.security.quantum.symmetric import QuantumSymmetricCipher
from src.security.quantum.key_manager import QuantumKeyManager
from src.security.quantum.hybrid import HybridKeyExchange
from src.security.zkn.sealed_tunnel import SealedTunnel, TunnelEndpoint
from src.security.zkn.xotc_auth import XOTCAuthenticator
from src.security.zkn.micro_segmentation import MicroSegmentationPolicy, AccessVerdict
from src.security.zkn.zkn_manager import ZKNManager


class TestQuantumKEM:
    def test_keygen_encap_decap_roundtrip(self):
        kem = QuantumKEM()
        kp = kem.generate_keypair("test-kem")
        encap = kem.encapsulate(kp.public_key)
        recovered = kem.decapsulate(encap.ciphertext, kp.secret_key)
        assert recovered == encap.shared_secret

    def test_different_keypairs_produce_different_secrets(self):
        kem = QuantumKEM()
        kp1 = kem.generate_keypair("k1")
        kp2 = kem.generate_keypair("k2")
        assert kp1.fingerprint != kp2.fingerprint

    def test_fingerprint_is_deterministic(self):
        kem = QuantumKEM()
        kp = kem.generate_keypair("fp-test")
        import hashlib
        expected = hashlib.sha256(kp.public_key).hexdigest()[:16]
        assert kp.fingerprint == expected


class TestQuantumSigner:
    def test_sign_verify_roundtrip(self):
        signer = QuantumSigner()
        kp = signer.generate_keypair("test-sig")
        data = b"S3M tactical payload"
        sig = signer.sign(data, kp.secret_key)
        assert signer.verify(data, sig, kp.public_key) is True

    def test_tampered_data_fails_verification(self):
        signer = QuantumSigner()
        kp = signer.generate_keypair("test-sig")
        sig = signer.sign(b"original", kp.secret_key)
        assert signer.verify(b"tampered", sig, kp.public_key) is False

    def test_wrong_key_fails_verification(self):
        signer = QuantumSigner()
        kp1 = signer.generate_keypair("k1")
        kp2 = signer.generate_keypair("k2")
        sig = signer.sign(b"data", kp1.secret_key)
        assert signer.verify(b"data", sig, kp2.public_key) is False


class TestSymmetricCipher:
    def test_encrypt_decrypt_roundtrip(self):
        cipher = QuantumSymmetricCipher()
        kem = QuantumKEM()
        kp = kem.generate_keypair()
        encap = kem.encapsulate(kp.public_key)
        session_key = cipher.derive_session_key(encap.shared_secret)
        payload = cipher.encrypt(b"classified intel", session_key, "layer-01-llm")
        recovered = cipher.decrypt(payload, session_key)
        assert recovered == b"classified intel"

    def test_tampered_ciphertext_fails(self):
        cipher = QuantumSymmetricCipher()
        key = cipher.derive_session_key(b"test-secret-material")
        payload = cipher.encrypt(b"original", key, "test")
        payload.ciphertext = b"\x00" * len(payload.ciphertext)
        with pytest.raises(Exception):
            cipher.decrypt(payload, key)

    def test_sequence_counter_increments(self):
        cipher = QuantumSymmetricCipher()
        key = cipher.derive_session_key(b"test")
        p1 = cipher.encrypt(b"a", key)
        p2 = cipher.encrypt(b"b", key)
        assert p2.sequence == p1.sequence + 1


class TestHybridKeyExchange:
    def test_full_handshake(self):
        hkx = HybridKeyExchange()
        init_sig = hkx.signer.generate_keypair("init")
        resp_kem = hkx.kem.generate_keypair("resp")
        result = hkx.initiate(init_sig.secret_key, resp_kem.public_key)
        recovered = hkx.respond(
            result.kem_ciphertext, resp_kem.secret_key,
            resp_kem.public_key, init_sig.public_key, result.signature,
        )
        assert recovered == result.combined_secret

    def test_tampered_signature_rejected(self):
        hkx = HybridKeyExchange()
        init_sig = hkx.signer.generate_keypair("init")
        resp_kem = hkx.kem.generate_keypair("resp")
        result = hkx.initiate(init_sig.secret_key, resp_kem.public_key)
        with pytest.raises(ValueError, match="invalid signature"):
            hkx.respond(
                result.kem_ciphertext, resp_kem.secret_key,
                resp_kem.public_key, init_sig.public_key,
                b"\x00" * len(result.signature),
            )


class TestSealedTunnel:
    def test_establish_send_receive(self):
        kem = QuantumKEM()
        signer = QuantumSigner()
        init_kem = kem.generate_keypair("init")
        init_sig = signer.generate_keypair("init")
        resp_kem = kem.generate_keypair("resp")
        resp_sig = signer.generate_keypair("resp")

        initiator = TunnelEndpoint("layer-01-llm", "orchestrator", init_kem, init_sig, True)
        responder = TunnelEndpoint("layer-02-threat", "threat_manager", resp_kem, resp_sig)

        tunnel = SealedTunnel()
        sid = tunnel.establish_tunnel(initiator, responder)
        env = tunnel.send(sid, b"threat assessment request", init_sig.secret_key, "layer-01-llm")
        plaintext = tunnel.receive(env, init_sig.public_key)
        assert plaintext == b"threat assessment request"

    def test_destroy_tunnel(self):
        kem = QuantumKEM()
        signer = QuantumSigner()
        i = TunnelEndpoint("l1", "p1", kem.generate_keypair(), signer.generate_keypair(), True)
        r = TunnelEndpoint("l2", "p2", kem.generate_keypair(), signer.generate_keypair())
        tunnel = SealedTunnel()
        sid = tunnel.establish_tunnel(i, r)
        assert tunnel.destroy_tunnel(sid) is True
        assert tunnel.destroy_tunnel(sid) is False

    def test_invalid_signature_rejected(self):
        kem = QuantumKEM()
        signer = QuantumSigner()
        i = TunnelEndpoint("l1", "p1", kem.generate_keypair(), signer.generate_keypair(), True)
        r = TunnelEndpoint("l2", "p2", kem.generate_keypair(), signer.generate_keypair())
        tunnel = SealedTunnel()
        sid = tunnel.establish_tunnel(i, r)
        env = tunnel.send(sid, b"data", i.sig_keypair.secret_key, "l1")
        env["signature"] = "00" * 64
        wrong_pub = signer.generate_keypair("wrong").public_key
        with pytest.raises(ValueError, match="BREACH"):
            tunnel.receive(env, wrong_pub)


class TestXOTCAuth:
    def test_issue_and_verify(self):
        signer = QuantumSigner()
        kp = signer.generate_keypair("auth")
        auth = XOTCAuthenticator(signer)
        raw_code, record = auth.issue_code("layer-01-llm", "orchestrator", kp.secret_key)
        assert auth.verify_code(record.code_id, raw_code, kp.public_key) is True

    def test_replay_fails(self):
        signer = QuantumSigner()
        kp = signer.generate_keypair("auth")
        auth = XOTCAuthenticator(signer)
        raw_code, record = auth.issue_code("layer-01-llm", "orchestrator", kp.secret_key)
        auth.verify_code(record.code_id, raw_code, kp.public_key)
        assert auth.verify_code(record.code_id, raw_code, kp.public_key) is False

    def test_wrong_code_fails(self):
        signer = QuantumSigner()
        kp = signer.generate_keypair("auth")
        auth = XOTCAuthenticator(signer)
        _, record = auth.issue_code("layer-01-llm", "orchestrator", kp.secret_key)
        assert auth.verify_code(record.code_id, "wrong-code", kp.public_key) is False

    def test_cleanup_expired(self):
        import time
        signer = QuantumSigner()
        kp = signer.generate_keypair("auth")
        auth = XOTCAuthenticator(signer)
        auth.issue_code("l1", "p1", kp.secret_key, ttl=0)
        time.sleep(0.01)
        purged = auth.cleanup_expired()
        assert purged >= 1


class TestMicroSegmentation:
    def test_allowed_flow(self):
        policy = MicroSegmentationPolicy()
        verdict = policy.evaluate(
            "layer-02-threat", "suricata_adapter", "layer-01-llm", "orchestrator"
        )
        assert verdict == AccessVerdict.ALLOW

    def test_denied_flow(self):
        policy = MicroSegmentationPolicy()
        verdict = policy.evaluate(
            "layer-04-simulation", "wargame", "layer-08-comms", "relay"
        )
        assert verdict == AccessVerdict.DENY

    def test_bidirectional_rule(self):
        policy = MicroSegmentationPolicy()
        fwd = policy.evaluate("layer-03-autonomy", "bt_engine", "layer-04-simulation", "gazebo")
        rev = policy.evaluate("layer-04-simulation", "gazebo", "layer-03-autonomy", "bt_engine")
        assert fwd == AccessVerdict.ALLOW
        assert rev == AccessVerdict.ALLOW

    def test_security_shell_accesses_all(self):
        policy = MicroSegmentationPolicy()
        verdict = policy.evaluate("layer-10-security", "scanner", "layer-08-comms", "relay")
        assert verdict == AccessVerdict.ALLOW


class TestZKNManager:
    def test_full_lifecycle(self, tmp_path):
        mgr = ZKNManager(keys_dir=str(tmp_path / "keys"))
        result = mgr.bootstrap()
        assert result["status"] == "bootstrapped"
        assert result["layers"] == 14

        tunnel = mgr.open_tunnel(
            "layer-02-threat", "threat_manager", "layer-07-cyber", "soc_manager"
        )
        assert "session_id" in tunnel

        status = mgr.get_status()
        assert status["active_tunnels"] >= 1
        assert status["bootstrapped"] is True

    def test_denied_tunnel_raises(self, tmp_path):
        mgr = ZKNManager(keys_dir=str(tmp_path / "keys"))
        mgr.bootstrap()
        with pytest.raises(PermissionError, match="DENY"):
            mgr.open_tunnel(
                "layer-04-simulation", "wargame", "layer-08-comms", "relay"
            )

    def test_authenticate_process(self, tmp_path):
        mgr = ZKNManager(keys_dir=str(tmp_path / "keys"))
        mgr.bootstrap()
        auth = mgr.authenticate_process("layer-01-llm", "orchestrator")
        assert "raw_code" in auth
        assert auth["expires_in_seconds"] == 30

    def test_key_rotation(self, tmp_path):
        mgr = ZKNManager(keys_dir=str(tmp_path / "keys"))
        mgr.bootstrap()
        results = mgr.rotate_all_keys()
        assert len(results) == 14


class TestPerimeterShield:
    def test_audit_returns_report(self):
        from src.security.perimeter.invisibility_enforcer import InvisibilityEnforcer
        enforcer = InvisibilityEnforcer()
        report = enforcer.audit()
        assert hasattr(report, "is_invisible")
        assert hasattr(report, "findings")

    def test_firewall_rules_generated(self):
        from src.security.perimeter.invisibility_enforcer import InvisibilityEnforcer
        result = InvisibilityEnforcer().enforce_outbound_only()
        assert "rules" in result
        assert any("DROP" in r for r in result["rules"])
