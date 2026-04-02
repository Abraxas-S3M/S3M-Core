import hashlib
import json
import threading
from datetime import timedelta

import pytest
from pydantic import ValidationError

from src.security.model_trust import (
    ArtifactManifest,
    CheckOutcome,
    ModelBlockedError,
    ModelDomain,
    ModelIdentity,
    ModelRegistration,
    ModelSigner,
    ModelTrustRegistry,
    QuantizationType,
    RuntimeType,
    SignedMetadata,
    TrustCheckName,
    TrustEnforcer,
    TrustState,
    check_artifact_hash,
    check_behavioral_drift,
    check_registration_age,
    check_runtime_match,
    check_signature,
    check_trust_state,
    check_version_allowlist,
    register_s3m_engines,
)

# NOTE: src/security/__init__.py already existed and is intentionally not modified.


@pytest.fixture
def signing_key() -> bytes:
    return b"s3m-test-signing-key-32bytes!!!!"


@pytest.fixture
def signer(signing_key: bytes) -> ModelSigner:
    return ModelSigner(signing_key, "test-key")


@pytest.fixture
def registry(signer: ModelSigner) -> ModelTrustRegistry:
    return ModelTrustRegistry(signer)


@pytest.fixture
def sample_identity() -> ModelIdentity:
    return ModelIdentity(
        name="Test-LLM",
        provider="TestCorp",
        version="1.0",
        domain=ModelDomain.TACTICAL,
        parameter_count="7B",
        quantization=QuantizationType.Q4_K_M,
        runtime=RuntimeType.LLAMA_CPP,
    )


@pytest.fixture
def sample_bytes() -> bytes:
    return b"fake model weights " * 1000


@pytest.fixture
def registered(registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes):
    signed = registry.register(sample_identity, artifact_bytes=sample_bytes)
    return registry, sample_identity, signed


def _metadata_hash(signature: str, key_id: str, signed_at) -> str:
    return hashlib.sha256((signature + key_id + signed_at.isoformat()).encode("utf-8")).hexdigest()


class TestModelIdentity:
    def test_auto_uuid(self):
        identity = ModelIdentity(
            name="X",
            provider="Y",
            version="1.0",
            domain=ModelDomain.UNKNOWN,
            parameter_count="1B",
        )
        assert identity.model_id

    def test_blank_name_rejected(self):
        with pytest.raises(ValidationError):
            ModelIdentity(
                name="   ",
                provider="Y",
                version="1.0",
                domain=ModelDomain.UNKNOWN,
                parameter_count="1B",
            )

    def test_canonical_json_is_deterministic(self, sample_identity: ModelIdentity):
        assert sample_identity.canonical_json() == sample_identity.canonical_json()

    def test_canonical_json_excludes_model_id_and_registered_at(self, sample_identity: ModelIdentity):
        payload = json.loads(sample_identity.canonical_json())
        assert "model_id" not in payload
        assert "registered_at" not in payload

    def test_canonical_json_includes_name_provider_version(self, sample_identity: ModelIdentity):
        payload = json.loads(sample_identity.canonical_json())
        assert payload["name"] == "Test-LLM"
        assert payload["provider"] == "TestCorp"
        assert payload["version"] == "1.0"

    def test_frozen(self, sample_identity: ModelIdentity):
        with pytest.raises(ValidationError):
            sample_identity.name = "Mutated"

    def test_arabic_name_optional(self):
        identity = ModelIdentity(
            name="Arabic-Test",
            name_ar="اختبار",
            provider="SDAIA",
            version="1.0",
            domain=ModelDomain.ARABIC_NLP,
            parameter_count="7B",
        )
        assert identity.name_ar == "اختبار"


class TestArtifactManifest:
    def test_from_bytes_computes_sha256(self, sample_identity: ModelIdentity, sample_bytes: bytes):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, sample_bytes)
        assert manifest.artifact_sha256 == hashlib.sha256(sample_bytes).hexdigest()

    def test_from_bytes_size_correct(self, sample_identity: ModelIdentity, sample_bytes: bytes):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, sample_bytes)
        assert manifest.artifact_size_bytes == len(sample_bytes)

    def test_empty_bytes_handled(self, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"")
        assert manifest.artifact_sha256 == hashlib.sha256(b"").hexdigest()
        assert manifest.artifact_size_bytes == 0

    def test_frozen(self, sample_identity: ModelIdentity, sample_bytes: bytes):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, sample_bytes)
        with pytest.raises(ValidationError):
            manifest.artifact_sha256 = "bad"


class TestModelSigner:
    def test_sign_produces_nonempty_signature(self, signer: ModelSigner, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        assert isinstance(signed.signature, str)
        assert signed.signature

    def test_signature_is_hex_string(self, signer: ModelSigner, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        assert all(c in "0123456789abcdef" for c in signed.signature)

    def test_metadata_hash_nonempty(self, signer: ModelSigner, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        assert signed.metadata_hash

    def test_verify_returns_true_for_valid_metadata(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        assert signer.verify(signed) is True

    def test_verify_returns_false_after_tampering_signature(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        tampered = signed.model_copy(update={"signature": "0" * 64})
        assert signer.verify(tampered) is False

    def test_verify_returns_false_after_tampering_key_id(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        tampered = signed.model_copy(update={"signing_key_id": "wrong-key"})
        assert signer.verify(tampered) is False

    def test_different_keys_produce_different_signatures(self, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signer_one = ModelSigner(b"first-key", "k1")
        signer_two = ModelSigner(b"second-key", "k2")
        signed_one = signer_one.sign(sample_identity, manifest)
        signed_two = signer_two.sign(sample_identity, manifest)
        assert signed_one.signature != signed_two.signature

    def test_same_inputs_produce_same_signature(self, signer: ModelSigner, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        first = signer.sign(sample_identity, manifest)
        second = signer.sign(sample_identity, manifest)
        assert first.signature == second.signature


class TestTrustChecks:
    def test_check_signature_passes_valid(self, signer: ModelSigner, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        result = check_signature(signed, b"s3m-test-signing-key-32bytes!!!!")
        assert result.outcome == CheckOutcome.PASSED

    def test_check_signature_fails_tampered_signature(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        tampered = signed.model_copy(update={"signature": "f" * 64})
        result = check_signature(tampered, b"s3m-test-signing-key-32bytes!!!!")
        assert result.outcome == CheckOutcome.FAILED
        assert result.blocking() is True

    def test_check_signature_fails_tampered_metadata_hash(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        tampered = signed.model_copy(update={"metadata_hash": "a" * 64})
        result = check_signature(tampered, b"s3m-test-signing-key-32bytes!!!!")
        assert result.outcome == CheckOutcome.FAILED

    def test_check_artifact_hash_passes_matching_bytes(self, sample_identity: ModelIdentity):
        data = b"artifact-data"
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, data)
        result = check_artifact_hash(manifest, data)
        assert result.outcome == CheckOutcome.PASSED

    def test_check_artifact_hash_fails_wrong_bytes(self, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"A")
        result = check_artifact_hash(manifest, b"B")
        assert result.outcome == CheckOutcome.FAILED
        assert result.blocking() is True

    def test_check_artifact_hash_skipped_when_none(self, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"A")
        result = check_artifact_hash(manifest, None)
        assert result.outcome == CheckOutcome.SKIPPED

    def test_check_version_allowlist_passes_empty_list(self, sample_identity: ModelIdentity):
        result = check_version_allowlist(sample_identity, [])
        assert result.outcome == CheckOutcome.PASSED

    def test_check_version_allowlist_passes_version_in_list(self, sample_identity: ModelIdentity):
        result = check_version_allowlist(sample_identity, ["1.0", "2.0"])
        assert result.outcome == CheckOutcome.PASSED

    def test_check_version_allowlist_fails_version_not_in_list(self, sample_identity: ModelIdentity):
        identity = sample_identity.model_copy(update={"version": "3.0"})
        result = check_version_allowlist(identity, ["1.0"])
        assert result.outcome == CheckOutcome.FAILED

    def test_check_runtime_match_passes(self, sample_identity: ModelIdentity):
        result = check_runtime_match(sample_identity, RuntimeType.LLAMA_CPP)
        assert result.outcome == CheckOutcome.PASSED

    def test_check_runtime_match_fails_mismatch(self, sample_identity: ModelIdentity):
        result = check_runtime_match(sample_identity, RuntimeType.TENSORRT)
        assert result.outcome == CheckOutcome.FAILED

    def test_check_runtime_match_warning_on_unknown(self, sample_identity: ModelIdentity):
        result = check_runtime_match(sample_identity, RuntimeType.UNKNOWN)
        assert result.outcome == CheckOutcome.WARNING

    def test_check_registration_age_passes_fresh(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity
    ):
        signed = registry.register(sample_identity, artifact_bytes=b"abc")
        registration = registry.get_registration(sample_identity.model_id)
        assert registration is not None
        result = check_registration_age(registration)
        assert signed
        assert result.outcome == CheckOutcome.PASSED

    def test_check_registration_age_fails_expired(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        old_dt = signed.signed_at - timedelta(days=100)
        tampered = signed.model_copy(
            update={
                "signed_at": old_dt,
                "metadata_hash": _metadata_hash(signed.signature, signed.signing_key_id, old_dt),
            }
        )
        registration = ModelRegistration(
            signed_metadata=tampered,
            max_age_days=90.0,
        )
        result = check_registration_age(registration)
        assert result.outcome == CheckOutcome.FAILED

    def test_check_registration_age_warning_near_expiry(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        old_dt = signed.signed_at - timedelta(days=85)
        tampered = signed.model_copy(
            update={
                "signed_at": old_dt,
                "metadata_hash": _metadata_hash(signed.signature, signed.signing_key_id, old_dt),
            }
        )
        registration = ModelRegistration(
            signed_metadata=tampered,
            max_age_days=90.0,
        )
        result = check_registration_age(registration)
        assert result.outcome == CheckOutcome.WARNING

    def test_check_trust_state_passes_trusted(self, signer: ModelSigner, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        registration = ModelRegistration(signed_metadata=signed, current_trust=TrustState.TRUSTED)
        result = check_trust_state(registration)
        assert result.outcome == CheckOutcome.PASSED

    def test_check_trust_state_fails_compromised(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        registration = ModelRegistration(signed_metadata=signed, current_trust=TrustState.COMPROMISED)
        result = check_trust_state(registration)
        assert result.outcome == CheckOutcome.FAILED
        assert result.blocking() is True

    def test_check_trust_state_fails_revoked(self, signer: ModelSigner, sample_identity: ModelIdentity):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        registration = ModelRegistration(signed_metadata=signed, revoked=True)
        result = check_trust_state(registration)
        assert result.outcome == CheckOutcome.FAILED
        assert result.blocking() is True

    def test_check_behavioral_drift_skipped_when_none(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        registration = ModelRegistration(signed_metadata=signed)
        result = check_behavioral_drift(registration, None)
        assert result.outcome == CheckOutcome.SKIPPED

    def test_check_behavioral_drift_passes_within_threshold(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        registration = ModelRegistration(signed_metadata=signed, behavioral_drift_threshold=0.15)
        result = check_behavioral_drift(registration, 0.05)
        assert result.outcome == CheckOutcome.PASSED

    def test_check_behavioral_drift_fails_above_threshold(
        self, signer: ModelSigner, sample_identity: ModelIdentity
    ):
        manifest = ArtifactManifest.from_bytes(sample_identity.model_id, b"abc")
        signed = signer.sign(sample_identity, manifest)
        registration = ModelRegistration(signed_metadata=signed, behavioral_drift_threshold=0.15)
        result = check_behavioral_drift(registration, 0.25)
        assert result.outcome == CheckOutcome.FAILED


class TestModelTrustRegistryInvalidModelFlagged:
    def test_register_stores_model(self, registry: ModelTrustRegistry, sample_identity: ModelIdentity):
        registry.register(sample_identity, artifact_bytes=b"abc")
        assert registry.get_registration(sample_identity.model_id) is not None

    def test_attest_unregistered_raises_keyerror(self, registry: ModelTrustRegistry):
        with pytest.raises(KeyError):
            registry.attest("missing-model")

    def test_attest_unverified_model_returns_record(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity
    ):
        registry.register(sample_identity, artifact_bytes=None)
        record = registry.attest(sample_identity.model_id)
        assert record.model_id == sample_identity.model_id

    def test_attest_with_correct_bytes_returns_trusted(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        record = registry.attest(
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
            drift_score=0.05,
        )
        assert record.trust_state == TrustState.TRUSTED

    def test_attest_with_wrong_bytes_returns_compromised(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity
    ):
        registry.register(sample_identity, artifact_bytes=b"A" * 100)
        record = registry.attest(
            sample_identity.model_id,
            artifact_bytes=b"B" * 100,
            actual_runtime=RuntimeType.LLAMA_CPP,
        )
        assert record.trust_state == TrustState.COMPROMISED

    def test_invalid_signature_flags_compromised(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        registration = registry.get_registration(sample_identity.model_id)
        assert registration is not None
        bad_signed = registration.signed_metadata.model_copy(update={"signature": "f" * 64})
        registration.signed_metadata = bad_signed
        record = registry.attest(
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
        )
        assert record.trust_state == TrustState.COMPROMISED

    def test_blocked_when_compromised(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity
    ):
        registry.register(sample_identity, artifact_bytes=b"A" * 100)
        record = registry.attest(
            sample_identity.model_id,
            artifact_bytes=b"B" * 100,
            actual_runtime=RuntimeType.LLAMA_CPP,
        )
        assert record.blocked is True

    def test_block_reason_populated(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity
    ):
        registry.register(sample_identity, artifact_bytes=b"A")
        record = registry.attest(
            sample_identity.model_id,
            artifact_bytes=b"B",
            actual_runtime=RuntimeType.LLAMA_CPP,
        )
        assert record.block_reason is not None
        assert record.block_reason != ""


class TestModelTrustRegistryTrustStatePropagates:
    def test_trust_history_grows_with_each_attest(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        for _ in range(3):
            registry.attest(
                sample_identity.model_id,
                artifact_bytes=sample_bytes,
                actual_runtime=RuntimeType.LLAMA_CPP,
                drift_score=0.01,
            )
        registration = registry.get_registration(sample_identity.model_id)
        assert registration is not None
        assert len(registration.trust_history) == 3

    def test_current_trust_updated_after_attest(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        record = registry.attest(
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
            drift_score=0.01,
        )
        assert registry.trust_state(sample_identity.model_id) == record.trust_state

    def test_last_attested_at_updated(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        registry.attest(
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
            drift_score=0.01,
        )
        registration = registry.get_registration(sample_identity.model_id)
        assert registration is not None
        assert registration.last_attested_at is not None

    def test_audit_log_returns_recent_records(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        for _ in range(5):
            registry.attest(
                sample_identity.model_id,
                artifact_bytes=sample_bytes,
                actual_runtime=RuntimeType.LLAMA_CPP,
                drift_score=0.01,
            )
        audit = registry.audit_log(n=2)
        assert len(audit) == 2

    def test_list_models_returns_all_identities(self, registry: ModelTrustRegistry):
        one = ModelIdentity(
            name="One",
            provider="P",
            version="1",
            domain=ModelDomain.TACTICAL,
            parameter_count="1B",
        )
        two = ModelIdentity(
            name="Two",
            provider="P",
            version="1",
            domain=ModelDomain.PLANNING,
            parameter_count="2B",
        )
        registry.register(one)
        registry.register(two)
        models = registry.list_models()
        names = {m.name for m in models}
        assert names == {"One", "Two"}

    def test_trust_state_query_returns_current(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        registry.attest(
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
            drift_score=0.01,
        )
        assert registry.trust_state(sample_identity.model_id) == TrustState.TRUSTED

    def test_overall_confidence_one_when_all_pass(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes, version_allowlist=["1.0"])
        record = registry.attest(
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
            drift_score=0.01,
        )
        assert record.overall_confidence == 1.0


class TestModelTrustRegistryCompromisedModelBlocked:
    def test_revoke_sets_revoked_true(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        registry.revoke(sample_identity.model_id, reason="Operator action")
        registration = registry.get_registration(sample_identity.model_id)
        assert registration is not None
        assert registration.revoked is True

    def test_revoke_sets_trust_state_revoked(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        registry.revoke(sample_identity.model_id, reason="Operator action")
        assert registry.trust_state(sample_identity.model_id) == TrustState.REVOKED

    def test_attest_after_revoke_returns_revoked_state(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        registry.revoke(sample_identity.model_id, reason="Operator action")
        record = registry.attest(
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
        )
        assert record.trust_state == TrustState.REVOKED

    def test_attest_after_revoke_is_blocked(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        registry.revoke(sample_identity.model_id, reason="Operator action")
        record = registry.attest(
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
        )
        assert record.blocked is True

    def test_revoke_unregistered_raises_keyerror(self, registry: ModelTrustRegistry):
        with pytest.raises(KeyError):
            registry.revoke("missing", reason="none")

    def test_compromised_after_tampered_artifact(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity
    ):
        registry.register(sample_identity, artifact_bytes=b"real")
        record = registry.attest(
            sample_identity.model_id,
            artifact_bytes=b"fake",
            actual_runtime=RuntimeType.LLAMA_CPP,
        )
        assert record.blocked is True
        assert record.trust_state == TrustState.COMPROMISED

    def test_trust_enforcer_raises_on_compromised(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity
    ):
        registry.register(sample_identity, artifact_bytes=b"good")
        enforcer = TrustEnforcer(
            registry,
            sample_identity.model_id,
            artifact_bytes=b"bad",
            actual_runtime=RuntimeType.LLAMA_CPP,
        )
        with pytest.raises(ModelBlockedError):
            enforcer.__enter__()

    def test_trust_enforcer_returns_record_when_trusted(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        enforcer = TrustEnforcer(
            registry,
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
            drift_score=0.01,
        )
        record = enforcer.__enter__()
        enforcer.__exit__(None, None, None)
        assert record.trust_state == TrustState.TRUSTED

    def test_model_blocked_error_contains_record(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity
    ):
        registry.register(sample_identity, artifact_bytes=b"good")
        enforcer = TrustEnforcer(
            registry,
            sample_identity.model_id,
            artifact_bytes=b"bad",
            actual_runtime=RuntimeType.LLAMA_CPP,
        )
        with pytest.raises(ModelBlockedError) as exc:
            enforcer.__enter__()
        assert exc.value.record.model_id == sample_identity.model_id

    def test_trust_enforcer_does_not_raise_when_raise_on_block_false(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity
    ):
        registry.register(sample_identity, artifact_bytes=b"good")
        enforcer = TrustEnforcer(
            registry,
            sample_identity.model_id,
            artifact_bytes=b"bad",
            actual_runtime=RuntimeType.LLAMA_CPP,
            raise_on_block=False,
        )
        record = enforcer.__enter__()
        enforcer.__exit__(None, None, None)
        assert record.blocked is True


class TestTrustEnforcer:
    def test_context_manager_enter_exit(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        with TrustEnforcer(
            registry,
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
            drift_score=0.01,
        ) as record:
            assert record.blocked is False

    def test_enforcer_attests_before_execution(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        with TrustEnforcer(
            registry,
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
            drift_score=0.01,
        ):
            pass
        assert len(registry.audit_log(50)) == 1

    def test_enforcer_with_correct_model_passes(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        with TrustEnforcer(
            registry,
            sample_identity.model_id,
            artifact_bytes=sample_bytes,
            actual_runtime=RuntimeType.LLAMA_CPP,
            drift_score=0.01,
        ) as record:
            assert record.trust_state == TrustState.TRUSTED

    def test_enforcer_blocks_compromised_model(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity
    ):
        registry.register(sample_identity, artifact_bytes=b"aaa")
        with pytest.raises(ModelBlockedError):
            with TrustEnforcer(
                registry,
                sample_identity.model_id,
                artifact_bytes=b"bbb",
                actual_runtime=RuntimeType.LLAMA_CPP,
            ):
                pass


class TestRegisterS3MEngines:
    def test_registers_four_engines(self, registry: ModelTrustRegistry):
        result = register_s3m_engines(registry)
        assert len(result) == 4

    def test_phi3_registered_with_correct_domain(self, registry: ModelTrustRegistry):
        result = register_s3m_engines(registry)
        phi3 = registry.get_registration(result["phi3"].model_id)
        assert phi3 is not None
        assert phi3.signed_metadata.identity.domain == ModelDomain.TACTICAL

    def test_allam_has_arabic_name(self, registry: ModelTrustRegistry):
        result = register_s3m_engines(registry)
        allam = registry.get_registration(result["allam"].model_id)
        assert allam is not None
        assert allam.signed_metadata.identity.name_ar is not None

    def test_allam_has_arabic_description(self, registry: ModelTrustRegistry):
        result = register_s3m_engines(registry)
        allam = registry.get_registration(result["allam"].model_id)
        assert allam is not None
        assert allam.signed_metadata.identity.description_ar is not None
        assert "SDAIA" in allam.signed_metadata.identity.description_ar

    def test_all_use_llama_cpp_runtime(self, registry: ModelTrustRegistry):
        result = register_s3m_engines(registry)
        for signed in result.values():
            registration = registry.get_registration(signed.model_id)
            assert registration is not None
            assert registration.signed_metadata.identity.runtime == RuntimeType.LLAMA_CPP

    def test_all_use_q4_k_m_quantization(self, registry: ModelTrustRegistry):
        result = register_s3m_engines(registry)
        for signed in result.values():
            registration = registry.get_registration(signed.model_id)
            assert registration is not None
            assert registration.signed_metadata.identity.quantization == QuantizationType.Q4_K_M


class TestConcurrency:
    def test_concurrent_registrations_safe(self, signer: ModelSigner):
        registry = ModelTrustRegistry(signer)
        errors = []

        def _register(i: int) -> None:
            try:
                identity = ModelIdentity(
                    name=f"Model-{i}",
                    provider="ThreadCorp",
                    version="1.0",
                    domain=ModelDomain.MULTI,
                    parameter_count="1B",
                    runtime=RuntimeType.LLAMA_CPP,
                    quantization=QuantizationType.Q4_K_M,
                )
                registry.register(identity, artifact_bytes=f"payload-{i}".encode("utf-8"))
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=_register, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(registry.list_models()) == 20

    def test_concurrent_attests_safe(
        self, registry: ModelTrustRegistry, sample_identity: ModelIdentity, sample_bytes: bytes
    ):
        registry.register(sample_identity, artifact_bytes=sample_bytes)
        errors = []

        def _attest() -> None:
            try:
                registry.attest(
                    sample_identity.model_id,
                    artifact_bytes=sample_bytes,
                    actual_runtime=RuntimeType.LLAMA_CPP,
                    drift_score=0.01,
                )
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=_attest) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        registration = registry.get_registration(sample_identity.model_id)
        assert registration is not None
        assert not errors
        assert len(registration.trust_history) == 20

