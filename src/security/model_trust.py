"""Runtime model trust and attestation for S3M engines."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
import hmac
import json
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid4_str() -> str:
    return str(uuid.uuid4())


class TrustState(str, Enum):
    """Current runtime trust posture for a registered model."""

    UNVERIFIED = "UNVERIFIED"
    TRUSTED = "TRUSTED"
    DEGRADED = "DEGRADED"
    COMPROMISED = "COMPROMISED"
    REVOKED = "REVOKED"


class ModelDomain(str, Enum):
    """Operational domain classification for an S3M model."""

    TACTICAL = "TACTICAL"
    REASONING = "REASONING"
    PLANNING = "PLANNING"
    ARABIC_NLP = "ARABIC_NLP"
    MULTI = "MULTI"
    UNKNOWN = "UNKNOWN"


class QuantizationType(str, Enum):
    """Model quantization type for edge deployment."""

    Q4_K_M = "Q4_K_M"
    Q5_K_M = "Q5_K_M"
    Q8_0 = "Q8_0"
    F16 = "F16"
    F32 = "F32"
    UNKNOWN = "UNKNOWN"


class RuntimeType(str, Enum):
    """Inference runtime in use for model execution."""

    LLAMA_CPP = "LLAMA_CPP"
    TENSORRT = "TENSORRT"
    ONNX = "ONNX"
    PYTORCH = "PYTORCH"
    CTRANSLATE2 = "CTRANSLATE2"
    UNKNOWN = "UNKNOWN"


class TrustCheckName(str, Enum):
    """Trust control points executed prior to model invocation."""

    SIGNATURE_VALID = "SIGNATURE_VALID"
    ARTIFACT_HASH_MATCH = "ARTIFACT_HASH_MATCH"
    VERSION_ALLOWLISTED = "VERSION_ALLOWLISTED"
    RUNTIME_MATCH = "RUNTIME_MATCH"
    REGISTRATION_CURRENT = "REGISTRATION_CURRENT"
    TRUST_STATE_VALID = "TRUST_STATE_VALID"
    BEHAVIORAL_DRIFT_OK = "BEHAVIORAL_DRIFT_OK"


class CheckOutcome(str, Enum):
    """Outcome of an individual trust check."""

    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    WARNING = "WARNING"


class ModelIdentity(BaseModel):
    """Immutable identity and operational metadata for a model."""

    model_config = ConfigDict(frozen=True)

    model_id: str = Field(default_factory=_uuid4_str)
    name: str
    name_ar: Optional[str] = None
    provider: str
    version: str
    domain: ModelDomain
    parameter_count: str
    quantization: QuantizationType = QuantizationType.UNKNOWN
    runtime: RuntimeType = RuntimeType.UNKNOWN
    hf_repo: Optional[str] = None
    local_path: Optional[str] = None
    registered_at: datetime = Field(default_factory=_utcnow)
    registered_by: str = "system"
    description: Optional[str] = None
    description_ar: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Model name must not be blank.")
        return value

    def canonical_json(self) -> str:
        """Return deterministic JSON payload used for HMAC signing."""
        payload: Dict[str, Any] = {
            "name": self.name,
            "provider": self.provider,
            "version": self.version,
            "domain": self.domain.value,
            "parameter_count": self.parameter_count,
            "quantization": self.quantization.value,
            "runtime": self.runtime.value,
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class ArtifactManifest(BaseModel):
    """Immutable artifact integrity manifest derived from model bytes."""

    model_config = ConfigDict(frozen=True)

    manifest_id: str = Field(default_factory=_uuid4_str)
    model_id: str
    artifact_sha256: str
    artifact_size_bytes: int = Field(ge=0)
    chunk_hashes: List[str] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=_utcnow)

    @classmethod
    def from_bytes(cls, model_id: str, data: bytes) -> "ArtifactManifest":
        """Build a manifest from in-memory model bytes."""
        digest = hashlib.sha256(data).hexdigest()
        size = len(data)
        chunk_hashes: List[str] = []
        chunk_size = 256 * 1024 * 1024
        if size > chunk_size:
            for idx in range(0, size, chunk_size):
                chunk_hashes.append(hashlib.sha256(data[idx : idx + chunk_size]).hexdigest())
        return cls(
            model_id=model_id,
            artifact_sha256=digest,
            artifact_size_bytes=size,
            chunk_hashes=chunk_hashes,
        )


class SignedMetadata(BaseModel):
    """Immutable signed identity + artifact metadata envelope."""

    model_config = ConfigDict(frozen=True)

    signed_id: str = Field(default_factory=_uuid4_str)
    model_id: str
    identity: ModelIdentity
    manifest: ArtifactManifest
    signature: str
    signing_key_id: str
    signed_at: datetime = Field(default_factory=_utcnow)
    metadata_hash: str


class TrustCheckResult(BaseModel):
    """Immutable result for a single trust check."""

    model_config = ConfigDict(frozen=True)

    check_name: TrustCheckName
    outcome: CheckOutcome
    detail: str
    detail_ar: Optional[str] = None
    measured_value: Optional[float] = None
    threshold: Optional[float] = None

    def passed(self) -> bool:
        """Return True when the check outcome is PASSED."""
        return self.outcome == CheckOutcome.PASSED

    def blocking(self) -> bool:
        """Return True if this failed check must block model execution."""
        blocking_checks = {
            TrustCheckName.SIGNATURE_VALID,
            TrustCheckName.ARTIFACT_HASH_MATCH,
            TrustCheckName.TRUST_STATE_VALID,
        }
        return self.outcome == CheckOutcome.FAILED and self.check_name in blocking_checks


class TrustRecord(BaseModel):
    """Immutable evidence record for a trust evaluation event."""

    model_config = ConfigDict(frozen=True)

    record_id: str = Field(default_factory=_uuid4_str)
    model_id: str
    model_name: str
    trust_state: TrustState
    check_results: List[TrustCheckResult]
    blocked: bool
    block_reason: Optional[str] = None
    block_reason_ar: Optional[str] = None
    overall_confidence: float = Field(ge=0.0, le=1.0)
    call_context: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_utcnow)
    evaluation_ms: float = Field(ge=0.0)

    def passed_checks(self) -> List[TrustCheckResult]:
        """Return checks that passed successfully."""
        return [check for check in self.check_results if check.outcome == CheckOutcome.PASSED]

    def failed_checks(self) -> List[TrustCheckResult]:
        """Return checks that failed."""
        return [check for check in self.check_results if check.outcome == CheckOutcome.FAILED]

    def blocking_failures(self) -> List[TrustCheckResult]:
        """Return failed checks that should block execution."""
        return [check for check in self.check_results if check.blocking()]


class ModelRegistration(BaseModel):
    """Mutable runtime registration and trust lifecycle state."""

    registration_id: str = Field(default_factory=_uuid4_str)
    signed_metadata: SignedMetadata
    current_trust: TrustState = TrustState.UNVERIFIED
    version_allowlist: List[str] = Field(default_factory=list)
    max_age_days: float = Field(default=90.0, gt=0)
    revoked: bool = False
    revoke_reason: Optional[str] = None
    revoke_reason_ar: Optional[str] = None
    last_attested_at: Optional[datetime] = None
    trust_history: List[TrustRecord] = Field(default_factory=list)
    behavioral_drift_threshold: float = Field(default=0.15, ge=0.0, le=1.0)

    def revoke(self, reason: str, reason_ar: str = "") -> None:
        """Revoke model execution authority immediately."""
        self.revoked = True
        self.current_trust = TrustState.REVOKED
        self.revoke_reason = reason
        self.revoke_reason_ar = reason_ar or None

    def record_attestation(self, record: TrustRecord) -> None:
        """Append a trust record and update current trust status."""
        self.trust_history.append(record)
        self.current_trust = record.trust_state
        self.last_attested_at = record.timestamp

    def age_days(self) -> float:
        """Return registration age in days from signed metadata timestamp."""
        delta = _utcnow() - self.signed_metadata.signed_at
        return delta.total_seconds() / 86400.0


def check_signature(signed_metadata: SignedMetadata, signing_key: bytes) -> TrustCheckResult:
    """Validate metadata HMAC signature and envelope metadata hash."""
    expected_signature = hmac.new(
        signing_key,
        signed_metadata.identity.canonical_json().encode("utf-8"),
        "sha256",
    ).hexdigest()
    expected_metadata_hash = hashlib.sha256(
        (
            signed_metadata.signature
            + signed_metadata.signing_key_id
            + signed_metadata.signed_at.isoformat()
        ).encode("utf-8")
    ).hexdigest()

    signature_ok = hmac.compare_digest(expected_signature, signed_metadata.signature)
    metadata_ok = hmac.compare_digest(expected_metadata_hash, signed_metadata.metadata_hash)
    if signature_ok and metadata_ok:
        return TrustCheckResult(
            check_name=TrustCheckName.SIGNATURE_VALID,
            outcome=CheckOutcome.PASSED,
            detail="Metadata signature and envelope hash are valid.",
            detail_ar="التحقق من التوقيع",
        )
    return TrustCheckResult(
        check_name=TrustCheckName.SIGNATURE_VALID,
        outcome=CheckOutcome.FAILED,
        detail="Metadata signature or envelope hash is invalid.",
        detail_ar="فشل التحقق من التوقيع",
    )


def check_artifact_hash(
    manifest: ArtifactManifest, provided_bytes: Optional[bytes]
) -> TrustCheckResult:
    """Validate provided artifact bytes against registered SHA256."""
    if provided_bytes is None:
        return TrustCheckResult(
            check_name=TrustCheckName.ARTIFACT_HASH_MATCH,
            outcome=CheckOutcome.SKIPPED,
            detail="Artifact bytes not provided; integrity check skipped.",
            detail_ar="تخطي التحقق من البصمة",
        )
    measured_hash = hashlib.sha256(provided_bytes).hexdigest()
    if hmac.compare_digest(measured_hash, manifest.artifact_sha256):
        return TrustCheckResult(
            check_name=TrustCheckName.ARTIFACT_HASH_MATCH,
            outcome=CheckOutcome.PASSED,
            detail=f"Artifact hash matched. measured_sha256={measured_hash}",
            detail_ar="تطابق بصمة النموذج",
        )
    return TrustCheckResult(
        check_name=TrustCheckName.ARTIFACT_HASH_MATCH,
        outcome=CheckOutcome.FAILED,
        detail=(
            "Artifact hash mismatch. "
            f"expected_sha256={manifest.artifact_sha256}, measured_sha256={measured_hash}"
        ),
        detail_ar="عدم تطابق البصمة",
    )


def check_version_allowlist(identity: ModelIdentity, allowlist: List[str]) -> TrustCheckResult:
    """Validate that model version is allowlisted when configured."""
    if not allowlist:
        return TrustCheckResult(
            check_name=TrustCheckName.VERSION_ALLOWLISTED,
            outcome=CheckOutcome.PASSED,
            detail="No version restriction configured.",
            detail_ar="الإصدار مسموح به",
        )
    if identity.version in allowlist:
        return TrustCheckResult(
            check_name=TrustCheckName.VERSION_ALLOWLISTED,
            outcome=CheckOutcome.PASSED,
            detail=f"Version '{identity.version}' is allowlisted.",
            detail_ar="الإصدار مسموح به",
        )
    return TrustCheckResult(
        check_name=TrustCheckName.VERSION_ALLOWLISTED,
        outcome=CheckOutcome.FAILED,
        detail=f"Version '{identity.version}' is not in allowlist.",
        detail_ar="الإصدار غير مسموح به",
    )


def check_runtime_match(identity: ModelIdentity, actual_runtime: RuntimeType) -> TrustCheckResult:
    """Validate actual inference runtime against registered runtime."""
    expected = identity.runtime
    if expected == RuntimeType.UNKNOWN or actual_runtime == RuntimeType.UNKNOWN:
        return TrustCheckResult(
            check_name=TrustCheckName.RUNTIME_MATCH,
            outcome=CheckOutcome.WARNING,
            detail=f"Runtime unknown. expected={expected.value}, actual={actual_runtime.value}",
            detail_ar="بيئة التشغيل غير معروفة",
        )
    if expected == actual_runtime:
        return TrustCheckResult(
            check_name=TrustCheckName.RUNTIME_MATCH,
            outcome=CheckOutcome.PASSED,
            detail=f"Runtime matched. expected={expected.value}, actual={actual_runtime.value}",
            detail_ar="بيئة التشغيل متطابقة",
        )
    return TrustCheckResult(
        check_name=TrustCheckName.RUNTIME_MATCH,
        outcome=CheckOutcome.FAILED,
        detail=f"Runtime mismatch. expected={expected.value}, actual={actual_runtime.value}",
        detail_ar="بيئة التشغيل غير متطابقة",
    )


def check_registration_age(
    registration: ModelRegistration, now: Optional[datetime] = None
) -> TrustCheckResult:
    """Validate registration freshness against maximum age policy."""
    now_value = now or _utcnow()
    age = (now_value - registration.signed_metadata.signed_at).total_seconds() / 86400.0
    if age > registration.max_age_days:
        return TrustCheckResult(
            check_name=TrustCheckName.REGISTRATION_CURRENT,
            outcome=CheckOutcome.FAILED,
            detail=f"Registration expired. age_days={age:.3f}",
            detail_ar="انتهاء صلاحية التسجيل",
            measured_value=age,
            threshold=registration.max_age_days,
        )
    if age > registration.max_age_days * 0.9:
        return TrustCheckResult(
            check_name=TrustCheckName.REGISTRATION_CURRENT,
            outcome=CheckOutcome.WARNING,
            detail=f"Registration nearing expiry. age_days={age:.3f}",
            detail_ar="صلاحية التسجيل",
            measured_value=age,
            threshold=registration.max_age_days,
        )
    return TrustCheckResult(
        check_name=TrustCheckName.REGISTRATION_CURRENT,
        outcome=CheckOutcome.PASSED,
        detail=f"Registration current. age_days={age:.3f}",
        detail_ar="صلاحية التسجيل",
        measured_value=age,
        threshold=registration.max_age_days,
    )


def check_trust_state(registration: ModelRegistration) -> TrustCheckResult:
    """Validate mutable runtime trust state and revocation status."""
    if registration.revoked or registration.current_trust == TrustState.REVOKED:
        reason = registration.revoke_reason or "Model has been revoked."
        reason_ar = registration.revoke_reason_ar or "تم إلغاء الثقة بالنموذج"
        return TrustCheckResult(
            check_name=TrustCheckName.TRUST_STATE_VALID,
            outcome=CheckOutcome.FAILED,
            detail=f"Revoked model. reason={reason}",
            detail_ar=reason_ar,
        )
    if registration.current_trust == TrustState.COMPROMISED:
        return TrustCheckResult(
            check_name=TrustCheckName.TRUST_STATE_VALID,
            outcome=CheckOutcome.FAILED,
            detail="Model trust state is COMPROMISED.",
            detail_ar="حالة الثقة متدهورة وخطرة",
        )
    if registration.current_trust == TrustState.DEGRADED:
        return TrustCheckResult(
            check_name=TrustCheckName.TRUST_STATE_VALID,
            outcome=CheckOutcome.WARNING,
            detail="Model trust state is DEGRADED.",
            detail_ar="حالة الثقة متدهورة",
        )
    return TrustCheckResult(
        check_name=TrustCheckName.TRUST_STATE_VALID,
        outcome=CheckOutcome.PASSED,
        detail="Model trust state is valid.",
        detail_ar="حالة الثقة صالحة",
    )


def check_behavioral_drift(
    registration: ModelRegistration, drift_score: Optional[float]
) -> TrustCheckResult:
    """Validate behavioral drift score against configured threshold."""
    if drift_score is None:
        return TrustCheckResult(
            check_name=TrustCheckName.BEHAVIORAL_DRIFT_OK,
            outcome=CheckOutcome.SKIPPED,
            detail="Behavioral drift metric not provided; check skipped.",
            detail_ar="تخطي فحص الانجراف السلوكي",
        )
    if drift_score > registration.behavioral_drift_threshold:
        return TrustCheckResult(
            check_name=TrustCheckName.BEHAVIORAL_DRIFT_OK,
            outcome=CheckOutcome.FAILED,
            detail=(
                "Behavioral drift exceeds threshold. "
                f"drift_score={drift_score:.3f}, "
                f"threshold={registration.behavioral_drift_threshold:.3f}"
            ),
            detail_ar="تجاوز الانجراف السلوكي الحد المسموح",
            measured_value=float(drift_score),
            threshold=registration.behavioral_drift_threshold,
        )
    return TrustCheckResult(
        check_name=TrustCheckName.BEHAVIORAL_DRIFT_OK,
        outcome=CheckOutcome.PASSED,
        detail=(
            "Behavioral drift within threshold. "
            f"drift_score={drift_score:.3f}, "
            f"threshold={registration.behavioral_drift_threshold:.3f}"
        ),
        detail_ar="الانجراف السلوكي ضمن الحدود",
        measured_value=float(drift_score),
        threshold=registration.behavioral_drift_threshold,
    )


class ModelSigner:
    """HMAC signer/verifier for model identity metadata."""

    def __init__(self, signing_key: bytes, key_id: str = "default") -> None:
        """Initialize signer with in-memory HMAC key and key identifier."""
        self._key = signing_key
        self._key_id = key_id

    def sign(self, identity: ModelIdentity, manifest: ArtifactManifest) -> SignedMetadata:
        """Create a signed metadata envelope for model registration."""
        signed_at = _utcnow()
        signature = hmac.new(
            self._key, identity.canonical_json().encode("utf-8"), "sha256"
        ).hexdigest()
        metadata_hash = hashlib.sha256(
            (signature + self._key_id + signed_at.isoformat()).encode("utf-8")
        ).hexdigest()
        return SignedMetadata(
            model_id=identity.model_id,
            identity=identity,
            manifest=manifest,
            signature=signature,
            signing_key_id=self._key_id,
            signed_at=signed_at,
            metadata_hash=metadata_hash,
        )

    def verify(self, signed_metadata: SignedMetadata) -> bool:
        """Return True when signature and metadata envelope hash are valid."""
        expected_signature = hmac.new(
            self._key,
            signed_metadata.identity.canonical_json().encode("utf-8"),
            "sha256",
        ).hexdigest()
        expected_metadata_hash = hashlib.sha256(
            (
                signed_metadata.signature
                + signed_metadata.signing_key_id
                + signed_metadata.signed_at.isoformat()
            ).encode("utf-8")
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signed_metadata.signature) and hmac.compare_digest(
            expected_metadata_hash, signed_metadata.metadata_hash
        )


class ModelTrustRegistry:
    """Thread-safe authority for registration, attestation, and audit."""

    def __init__(
        self, signer: ModelSigner, max_age_days: float = 90.0, default_drift_threshold: float = 0.15
    ) -> None:
        """Initialize a trust registry with signer and default policies."""
        self._signer = signer
        self._max_age_days = max_age_days
        self._default_drift_threshold = default_drift_threshold
        self._lock = threading.RLock()
        self._registrations: Dict[str, ModelRegistration] = {}
        self._audit: List[TrustRecord] = []

    def register(
        self,
        identity: ModelIdentity,
        artifact_bytes: Optional[bytes] = None,
        version_allowlist: Optional[List[str]] = None,
    ) -> SignedMetadata:
        """Register and sign model metadata in the trust registry."""
        with self._lock:
            if artifact_bytes is not None:
                manifest = ArtifactManifest.from_bytes(identity.model_id, artifact_bytes)
            else:
                manifest = ArtifactManifest(
                    model_id=identity.model_id, artifact_sha256="", artifact_size_bytes=0
                )
            signed = self._signer.sign(identity, manifest)
            registration = ModelRegistration(
                signed_metadata=signed,
                current_trust=TrustState.UNVERIFIED,
                version_allowlist=list(version_allowlist or []),
                max_age_days=self._max_age_days,
                behavioral_drift_threshold=self._default_drift_threshold,
            )
            self._registrations[identity.model_id] = registration
            return signed

    def attest(
        self,
        model_id: str,
        artifact_bytes: Optional[bytes] = None,
        actual_runtime: Optional[RuntimeType] = None,
        drift_score: Optional[float] = None,
        call_context: Optional[Dict[str, Any]] = None,
    ) -> TrustRecord:
        """Run full trust checks and record attestation evidence."""
        with self._lock:
            if model_id not in self._registrations:
                raise KeyError(f"Model '{model_id}' is not registered.")

            start_time = time.time()
            registration = self._registrations[model_id]
            signed_metadata = registration.signed_metadata
            identity = signed_metadata.identity
            actual_rt = actual_runtime or RuntimeType.UNKNOWN

            checks: List[TrustCheckResult] = [
                check_signature(signed_metadata, self._signer._key),
                check_artifact_hash(signed_metadata.manifest, artifact_bytes),
                check_version_allowlist(identity, registration.version_allowlist),
                check_runtime_match(identity, actual_rt),
                check_registration_age(registration),
                check_trust_state(registration),
                check_behavioral_drift(registration, drift_score),
            ]

            blocking_failures = [check for check in checks if check.blocking()]
            any_failed = any(check.outcome == CheckOutcome.FAILED for check in checks)
            any_warning = any(check.outcome == CheckOutcome.WARNING for check in checks)

            if blocking_failures:
                trust_state = (
                    TrustState.REVOKED
                    if registration.revoked or registration.current_trust == TrustState.REVOKED
                    else TrustState.COMPROMISED
                )
            elif any_failed or any_warning:
                trust_state = TrustState.DEGRADED
            else:
                trust_state = TrustState.TRUSTED

            blocked = trust_state in {TrustState.COMPROMISED, TrustState.REVOKED}
            block_reason = "; ".join(check.detail for check in blocking_failures) or None
            block_reason_ar = (
                "; ".join(check.detail_ar for check in blocking_failures if check.detail_ar) or None
            )

            non_skipped = [check for check in checks if check.outcome != CheckOutcome.SKIPPED]
            passed_count = sum(1 for check in non_skipped if check.outcome == CheckOutcome.PASSED)
            overall_confidence = passed_count / max(1, len(non_skipped))
            evaluation_ms = (time.time() - start_time) * 1000.0

            record = TrustRecord(
                model_id=model_id,
                model_name=identity.name,
                trust_state=trust_state,
                check_results=checks,
                blocked=blocked,
                block_reason=block_reason,
                block_reason_ar=block_reason_ar,
                overall_confidence=overall_confidence,
                call_context=dict(call_context or {}),
                evaluation_ms=evaluation_ms,
            )
            registration.record_attestation(record)
            self._audit.append(record)
            return record

    def revoke(self, model_id: str, reason: str, reason_ar: str = "") -> None:
        """Revoke a registered model from execution."""
        with self._lock:
            registration = self._registrations.get(model_id)
            if registration is None:
                raise KeyError(f"Model '{model_id}' is not registered.")
            registration.revoke(reason, reason_ar)

    def get_registration(self, model_id: str) -> Optional[ModelRegistration]:
        """Return registration by model ID if present."""
        with self._lock:
            return self._registrations.get(model_id)

    def trust_state(self, model_id: str) -> TrustState:
        """Return current trust state or UNVERIFIED if unknown."""
        with self._lock:
            registration = self._registrations.get(model_id)
            if registration is None:
                return TrustState.UNVERIFIED
            return registration.current_trust

    def audit_log(self, n: int = 50) -> List[TrustRecord]:
        """Return the latest n trust records from registry audit."""
        with self._lock:
            return list(self._audit[-n:])

    def list_models(self) -> List[ModelIdentity]:
        """Return identities for all registered models."""
        with self._lock:
            return [reg.signed_metadata.identity for reg in self._registrations.values()]


class ModelBlockedError(Exception):
    """Raised when TrustEnforcer blocks model invocation."""

    def __init__(self, record: TrustRecord):
        """Initialize exception with blocking trust record context."""
        self.record = record
        super().__init__(
            f"Model '{record.model_name}' blocked. State={record.trust_state}. "
            f"Reason={record.block_reason}"
        )


class TrustEnforcer:
    """Context manager that gates execution behind trust attestation."""

    def __init__(
        self,
        registry: ModelTrustRegistry,
        model_id: str,
        artifact_bytes: Optional[bytes] = None,
        actual_runtime: Optional[RuntimeType] = None,
        drift_score: Optional[float] = None,
        call_context: Optional[Dict[str, Any]] = None,
        raise_on_block: bool = True,
    ) -> None:
        """Initialize enforcer with model invocation trust context."""
        self._registry = registry
        self._model_id = model_id
        self._artifact_bytes = artifact_bytes
        self._actual_runtime = actual_runtime
        self._drift_score = drift_score
        self._call_context = call_context
        self._raise_on_block = raise_on_block

    def __enter__(self) -> TrustRecord:
        """Attest model trust and optionally raise when execution is blocked."""
        record = self._registry.attest(
            model_id=self._model_id,
            artifact_bytes=self._artifact_bytes,
            actual_runtime=self._actual_runtime,
            drift_score=self._drift_score,
            call_context=self._call_context,
        )
        if record.blocked and self._raise_on_block:
            raise ModelBlockedError(record)
        return record

    def __exit__(self, *args: Any) -> None:
        """No-op context exit for trust enforcer."""
        return None


def create_default_registry(signing_key: bytes, key_id: str = "s3m-default") -> ModelTrustRegistry:
    """Create a default model trust registry with signer."""
    return ModelTrustRegistry(ModelSigner(signing_key, key_id))


def register_s3m_engines(
    registry: ModelTrustRegistry, version_allowlist: Optional[List[str]] = None
) -> Dict[str, SignedMetadata]:
    """Register canonical S3M engines with identity metadata only."""
    phi3 = ModelIdentity(
        name="Phi-3 Mini",
        provider="Microsoft",
        version="4k-instruct",
        domain=ModelDomain.TACTICAL,
        parameter_count="3.8B",
        quantization=QuantizationType.Q4_K_M,
        runtime=RuntimeType.LLAMA_CPP,
        hf_repo="microsoft/Phi-3-mini-4k-instruct-gguf",
        local_path="models/phi3/phi-3-mini-4k-instruct-q4_k_m.gguf",
    )
    grok = ModelIdentity(
        name="Grok",
        provider="xAI",
        version="1.0",
        domain=ModelDomain.REASONING,
        parameter_count="8B",
        quantization=QuantizationType.Q4_K_M,
        runtime=RuntimeType.LLAMA_CPP,
        hf_repo="xai-org/grok-1",
        local_path="models/grok/grok-8b-q4_k_m.gguf",
    )
    mistral = ModelIdentity(
        name="Mistral 7B",
        provider="Mistral AI",
        version="0.3",
        domain=ModelDomain.PLANNING,
        parameter_count="7B",
        quantization=QuantizationType.Q4_K_M,
        runtime=RuntimeType.LLAMA_CPP,
        hf_repo="mistralai/Mistral-7B-Instruct-v0.3",
        local_path="models/mistral/mistral-7b-instruct-v0.3-q4_k_m.gguf",
    )
    allam = ModelIdentity(
        name="ALLaM-7B",
        name_ar="نموذج اللغة العربية",
        provider="SDAIA",
        version="1.0",
        domain=ModelDomain.ARABIC_NLP,
        parameter_count="7B",
        quantization=QuantizationType.Q4_K_M,
        runtime=RuntimeType.LLAMA_CPP,
        hf_repo="sdaia/allam-7b",
        local_path="models/allam/allam-7b-q4_k_m.gguf",
        description_ar="نموذج اللغة العربية السيادي من SDAIA",
    )
    return {
        "phi3": registry.register(phi3, artifact_bytes=None, version_allowlist=version_allowlist),
        "grok": registry.register(grok, artifact_bytes=None, version_allowlist=version_allowlist),
        "mistral": registry.register(
            mistral, artifact_bytes=None, version_allowlist=version_allowlist
        ),
        "allam": registry.register(allam, artifact_bytes=None, version_allowlist=version_allowlist),
    }

