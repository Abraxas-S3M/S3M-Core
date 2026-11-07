"""Model admission gate for Cortex council engine loading.

Tactical context:
    Production nodes refuse any engine whose manifest fails integrity, format,
    scanner, eval, or admission-authority signature checks. Retired engines are
    never routable regardless of admission posture.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set

import yaml

from src.cortex.envelope import AdmissionSigner, HmacAdmissionSigner
from src.integrations.lechonk.shard_inventory import (
    ShardInventoryManifest,
    ShardVerificationResult,
    merge_variant_inventories,
    verify_shard_inventory,
)
from src.security.model_scanner import ModelScanner

logger = logging.getLogger("s3m.cortex.admission")

_ALLOWED_FORMATS = frozenset({"gguf", "safetensors"})
_FORBIDDEN_FORMATS = frozenset({"pickle", "bin", "pth", "pt"})
_DEFAULT_ENGINES_PATH = "configs/engines.yaml"
_DEFAULT_MANIFEST_DIR = "configs/model_manifests"


def deploy_mode() -> str:
    """Return deployment mode (production|lab)."""
    return os.environ.get("S3M_DEPLOY_MODE", "production").strip().lower()


def is_production() -> bool:
    return deploy_mode() == "production"


def load_engines_document(path: Optional[str] = None) -> Dict[str, Any]:
    """Load and parse the engines YAML document."""
    engines_path = Path(path or _DEFAULT_ENGINES_PATH)
    if not engines_path.is_file():
        raise FileNotFoundError(f"Engines config not found: {engines_path}")
    data = yaml.safe_load(engines_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("engines document must be a mapping")
    return data


def engine_config(engine_id: str, path: Optional[str] = None) -> Dict[str, Any]:
    doc = load_engines_document(path)
    engines = doc.get("engines") or {}
    cfg = engines.get(engine_id)
    if not isinstance(cfg, dict):
        raise KeyError(f"Unknown engine '{engine_id}'")
    return dict(cfg)


def council_role_map(path: Optional[str] = None) -> Dict[str, str]:
    doc = load_engines_document(path)
    council = doc.get("cortex_council") or {}
    return {str(role): str(engine) for role, engine in council.items()}


def quad_engine_bindings(path: Optional[str] = None) -> Dict[str, str]:
    doc = load_engines_document(path)
    bindings = doc.get("quad_engine_map") or {}
    return {str(quad_id): str(engine_id) for quad_id, engine_id in bindings.items()}


def is_engine_retired(engine_id: str, path: Optional[str] = None) -> bool:
    try:
        cfg = engine_config(engine_id, path)
    except KeyError:
        return False
    return str(cfg.get("status", "")).strip().lower() == "retired"


def is_engine_routable(engine_id: str, path: Optional[str] = None) -> bool:
    """Return True when an engine may be selected for Cortex/quad routing."""
    try:
        cfg = engine_config(engine_id, path)
    except KeyError:
        return False
    if str(cfg.get("status", "")).strip().lower() == "retired":
        return False
    admission = cfg.get("admission") or {}
    admission_status = str(admission.get("status", "active")).strip().lower()
    if admission_status in {"retired", "not_selected", "quarantine"}:
        return False
    if str(cfg.get("alias_of", "")).strip():
        return False
    return True


@dataclass(frozen=True)
class AdmissionDecision:
    """Result of an admission gate evaluation."""

    engine_id: str
    allowed: bool
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def explanation(self) -> str:
        if self.allowed and self.warnings:
            return "; ".join(self.warnings)
        return "; ".join(self.reasons) if self.reasons else "admitted"


class ModelAdmissionGate:
    """Evaluates per-engine manifests against production admission policy."""

    def __init__(
        self,
        *,
        engines_path: str = _DEFAULT_ENGINES_PATH,
        manifest_dir: str = _DEFAULT_MANIFEST_DIR,
        signer: Optional[AdmissionSigner] = None,
        scanner: Optional[ModelScanner] = None,
    ) -> None:
        self._engines_path = engines_path
        self._manifest_dir = Path(manifest_dir)
        self._signer = signer or HmacAdmissionSigner(signing_key=b"s3m-admission-test-key")
        self._scanner = scanner or ModelScanner()

    @property
    def signer(self) -> AdmissionSigner:
        return self._signer

    def resolve_manifest_id(self, engine_id: str) -> str:
        cfg = engine_config(engine_id, self._engines_path)
        manifest_id = str(cfg.get("manifest_id") or engine_id).strip()
        doc = load_engines_document(self._engines_path)
        aliases = doc.get("manifest_aliases") or {}
        return str(aliases.get(manifest_id, manifest_id))

    def load_manifest_admission(self, engine_id: str) -> Dict[str, Any]:
        cfg = engine_config(engine_id, self._engines_path)
        manifest_id = self.resolve_manifest_id(engine_id)
        manifest_path = self._resolve_manifest_path(manifest_id)
        merged: Dict[str, Any] = {}
        if manifest_path is not None:
            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            admission = data.get("admission") if isinstance(data, dict) else None
            if isinstance(admission, dict):
                merged.update(admission)
        engine_admission = cfg.get("admission")
        if isinstance(engine_admission, dict):
            merged.update(engine_admission)
        return merged

    def _resolve_manifest_path(self, manifest_id: str) -> Optional[Path]:
        if not self._manifest_dir.exists():
            return None
        doc = load_engines_document(self._engines_path)
        aliases: Dict[str, str] = dict(doc.get("manifest_aliases") or {})
        resolved = aliases.get(manifest_id, manifest_id)
        for stem in (resolved, manifest_id, resolved.replace("-", "_"), manifest_id.replace("-", "_")):
            for suffix in (".yaml", ".yml"):
                candidate = self._manifest_dir / f"{stem}{suffix}"
                if candidate.is_file():
                    return candidate
        return None

    @staticmethod
    def _sha256_file(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def evaluate(
        self,
        engine_id: str,
        *,
        model_path: Optional[str] = None,
        production: Optional[bool] = None,
    ) -> AdmissionDecision:
        reasons: List[str] = []
        warnings: List[str] = []

        try:
            cfg = engine_config(engine_id, self._engines_path)
        except KeyError:
            return AdmissionDecision(engine_id=engine_id, allowed=False, reasons=["unknown_engine"])

        if str(cfg.get("status", "")).strip().lower() == "retired":
            reason = str(cfg.get("retired_reason") or "engine retired")
            logger.warning("Refusing retired engine %s: %s", engine_id, reason)
            return AdmissionDecision(engine_id=engine_id, allowed=False, reasons=[f"retired: {reason}"])

        admission = self.load_manifest_admission(engine_id)
        prod = is_production() if production is None else bool(production)

        fmt = str(admission.get("format") or cfg.get("runtime") or "").strip().lower()
        if fmt in _FORBIDDEN_FORMATS:
            reasons.append(f"forbidden_format:{fmt}")
        elif fmt and fmt not in _ALLOWED_FORMATS:
            reasons.append(f"unsupported_format:{fmt}")
        elif not fmt:
            reasons.append("missing_format")

        sha_verified = bool(admission.get("sha256_verified", False))
        pinned = str(admission.get("pinned_sha256") or "").strip().lower()
        if not sha_verified:
            reasons.append("sha256_not_verified")
        elif pinned:
            if model_path:
                path_obj = Path(model_path)
                if path_obj.is_file():
                    measured = self._sha256_file(path_obj)
                    if measured != pinned:
                        reasons.append("sha256_mismatch")
            elif prod:
                reasons.append("sha256_unconfirmed_without_artifact")

        scanner_passed = bool(admission.get("scanner_passed", False))
        if not scanner_passed:
            reasons.append("scanner_not_passed")

        if not bool(admission.get("evals_passed", False)):
            reasons.append("evals_not_passed")

        signature = str(admission.get("signature") or "").strip()
        if not signature:
            if prod:
                reasons.append("unsigned_manifest")
            else:
                warnings.append("unsigned_manifest_allowed_in_lab")

        elif not self._signer.verify_fields(admission, signature):
            reasons.append("invalid_admission_signature")

        admission_status = str(admission.get("status", "active")).strip().lower()
        if admission_status in {"quarantine", "not_selected"}:
            reasons.append(f"admission_status:{admission_status}")

        if bool(admission.get("require_shard_inventory", False)):
            reasons.append("shard_inventory_not_verified_at_evaluate")

        allowed = len(reasons) == 0
        if not allowed:
            logger.warning(
                "Admission refused for engine=%s production=%s reasons=%s",
                engine_id,
                prod,
                reasons,
            )
        elif warnings:
            logger.warning(
                "Admission allowed with warnings engine=%s warnings=%s",
                engine_id,
                warnings,
            )
        return AdmissionDecision(engine_id=engine_id, allowed=allowed, reasons=reasons, warnings=warnings)

    def evaluate_shard_inventory(
        self,
        engine_id: str,
        artifact_root: str,
        *,
        variant_tag: Optional[str] = None,
    ) -> ShardVerificationResult:
        """
        Verify on-disk shards against the staged manifest inventory (fail-closed).

        Does not download quarantine objects; callers supply a local artifact_root.
        """
        manifest_path = self._resolve_manifest_path(self.resolve_manifest_id(engine_id))
        if manifest_path is None:
            return ShardVerificationResult(
                variant_tag=variant_tag or "",
                admitted=False,
                reasons=["manifest_missing"],
            )
        doc = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        inventories = merge_variant_inventories(doc if isinstance(doc, dict) else {})
        if variant_tag:
            inv = inventories.get(variant_tag)
        elif inventories:
            inv = next(iter(inventories.values()))
        else:
            return ShardVerificationResult(
                variant_tag=variant_tag or "",
                admitted=False,
                reasons=["inventory_not_configured"],
            )
        if inv is None:
            return ShardVerificationResult(
                variant_tag=variant_tag or "",
                admitted=False,
                reasons=["unknown_variant"],
            )
        return verify_shard_inventory(inv, Path(artifact_root))

    def admitted_with_shards(
        self,
        engine_id: str,
        artifact_root: str,
        *,
        variant_tag: Optional[str] = None,
        production: Optional[bool] = None,
    ) -> tuple[AdmissionDecision, ShardVerificationResult]:
        """Combine manifest admission checks with multi-shard verification."""
        decision = self.evaluate(engine_id, production=production)
        shard = self.evaluate_shard_inventory(engine_id, artifact_root, variant_tag=variant_tag)
        reasons = list(decision.reasons)
        if shard.admitted:
            reasons = [r for r in reasons if r != "shard_inventory_not_verified_at_evaluate"]
        else:
            reasons.extend(f"shards:{r}" for r in shard.reasons)
        allowed = len(reasons) == 0
        decision = AdmissionDecision(
            engine_id=decision.engine_id,
            allowed=allowed,
            reasons=reasons,
            warnings=decision.warnings,
        )
        return decision, shard

    def routable_engines(self) -> Set[str]:
        doc = load_engines_document(self._engines_path)
        engines = doc.get("engines") or {}
        return {eid for eid in engines if is_engine_routable(eid, self._engines_path)}


def registry_matches_engines_yaml(
    registry_engine_ids: List[str],
    bindings: Optional[Dict[str, str]] = None,
    path: Optional[str] = None,
) -> bool:
    """Verify quad registry IDs align with engines.yaml quad_engine_map."""
    expected = bindings or quad_engine_bindings(path)
    return set(registry_engine_ids) == set(expected.keys())


def registry_model_files_match(
    entries: Mapping[str, str],
    path: Optional[str] = None,
) -> bool:
    """Verify each quad binding resolves to the model_file in engines.yaml."""
    bindings = quad_engine_bindings(path)
    for quad_id, model_file in entries.items():
        engine_id = bindings.get(quad_id)
        if not engine_id:
            return False
        cfg = engine_config(engine_id, path)
        expected = str(cfg.get("model_file") or "").strip()
        if expected != str(model_file).strip():
            return False
    return True
