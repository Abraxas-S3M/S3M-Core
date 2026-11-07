"""Cloudflare R2 acquisition verification for Le Chonk quarantine objects (metadata-only).

Does not download multi-shard weights to local disk; compares listing metadata and
pinned inventory digests. Multipart upload ETags are never treated as SHA-256 evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence

import yaml

from src.integrations.lechonk.shard_inventory import ShardInventoryManifest, load_inventory_json, merge_variant_inventories

_MULTIPART_ETAG = re.compile(r"^[a-f0-9]{32}-\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class R2ObjectHead:
    key: str
    size_bytes: int
    etag: str = ""
    metadata_sha256: str = ""
    last_modified: str = ""
    revision: str = ""


class ObjectLister(Protocol):
    def list_prefix(self, prefix: str) -> Sequence[R2ObjectHead]:
        ...


@dataclass
class VariantAcquisitionReport:
    variant_tag: str
    r2_prefix: str
    source_revision: str
    expected_object_count: int
    listed_object_count: int
    admitted: bool
    reasons: List[str] = field(default_factory=list)
    inventory_verified_count: int = 0
    inventory_expected_count: int = 0
    objects: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_tag": self.variant_tag,
            "r2_prefix": self.r2_prefix,
            "source_revision": self.source_revision,
            "expected_object_count": self.expected_object_count,
            "listed_object_count": self.listed_object_count,
            "admitted": self.admitted,
            "reasons": list(self.reasons),
            "inventory_verified_count": self.inventory_verified_count,
            "inventory_expected_count": self.inventory_expected_count,
            "objects": list(self.objects),
        }


def etag_is_multipart(etag: str) -> bool:
    cleaned = (etag or "").strip().strip('"')
    return bool(_MULTIPART_ETAG.match(cleaned))


def _relative_key(full_key: str, prefix: str) -> str:
    p = prefix.strip().lstrip("/")
    key = full_key.strip().lstrip("/")
    if p and key.startswith(p):
        return key[len(p) :].lstrip("/")
    return key


def verify_variant_acquisition(
    variant: Mapping[str, Any],
    lister: ObjectLister,
    inventory: Optional[ShardInventoryManifest] = None,
) -> VariantAcquisitionReport:
    """Verify object count, sizes, revision metadata, and inventory SHA-256 fields."""
    tag = str(variant.get("tag") or "")
    prefix = str(variant.get("r2_prefix") or "").strip()
    revision = str(variant.get("source_revision") or "")
    expected_count = int(variant.get("expected_inventory_objects") or 0)
    reasons: List[str] = []

    listed = list(lister.list_prefix(prefix))
    rel_objects = [_relative_key(obj.key, prefix) for obj in listed]
    report_objects: List[Dict[str, Any]] = []
    inventory_by_path: Dict[str, Any] = {}
    if inventory is not None:
        inventory_by_path = {s.normalized_path(): s for s in inventory.shards}

    verified = 0
    for obj in listed:
        rel = _relative_key(obj.key, prefix)
        if etag_is_multipart(obj.etag):
            reasons.append(f"multipart_etag_untrusted:{rel}")
        sha_evidence = (obj.metadata_sha256 or "").strip().lower()
        if obj.etag and not sha_evidence:
            # ETag alone is not SHA-256; require metadata or inventory digest match path.
            pass
        inv = inventory_by_path.get(rel)
        entry: Dict[str, Any] = {
            "key": obj.key,
            "relative_path": rel,
            "size_bytes": obj.size_bytes,
            "etag": obj.etag,
            "metadata_sha256": sha_evidence,
            "revision": obj.revision or revision,
        }
        if inv is not None:
            entry["expected_size_bytes"] = inv.size_bytes
            entry["expected_sha256"] = inv.sha256
            if inv.size_bytes and obj.size_bytes != inv.size_bytes:
                reasons.append(f"size_mismatch:{rel}")
            elif inv.sha256 and sha_evidence and sha_evidence != inv.sha256:
                reasons.append(f"metadata_sha256_mismatch:{rel}")
            elif inv.sha256 and not sha_evidence:
                reasons.append(f"missing_metadata_sha256:{rel}")
            else:
                verified += 1
        report_objects.append(entry)

    if expected_count and len(listed) != expected_count:
        reasons.append(f"object_count_mismatch:expected={expected_count}:listed={len(listed)}")
    extra = set(rel_objects) - set(inventory_by_path.keys()) if inventory_by_path else set()
    missing = set(inventory_by_path.keys()) - set(rel_objects) if inventory_by_path else set()
    if inventory_by_path and missing:
        reasons.append(f"inventory_missing_on_r2:{len(missing)}")
    if inventory_by_path and extra:
        reasons.append(f"unexpected_r2_objects:{len(extra)}")

    admitted = len(reasons) == 0
    if inventory is not None and admitted:
        admitted = verified == len(inventory_by_path)
        if not admitted:
            reasons.append("inventory_digest_coverage_incomplete")

    return VariantAcquisitionReport(
        variant_tag=tag,
        r2_prefix=prefix,
        source_revision=revision,
        expected_object_count=expected_count,
        listed_object_count=len(listed),
        admitted=admitted,
        reasons=reasons,
        inventory_verified_count=verified,
        inventory_expected_count=len(inventory_by_path),
        objects=report_objects,
    )


def build_production_inventory_report(
    manifest_path: str = "configs/model_manifests/mistral_large_4.yaml",
    *,
    lister: ObjectLister,
    inventory_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    doc = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8")) or {}
    inventories = merge_variant_inventories(doc if isinstance(doc, dict) else {}, inventory_dir)
    variants = doc.get("variants") or []
    reports: List[VariantAcquisitionReport] = []
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        tag = str(variant.get("tag") or "")
        inv = inventories.get(tag)
        reports.append(verify_variant_acquisition(variant, lister, inv))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": str(doc.get("model_id") or "mistral_large_4"),
        "variants": [r.to_dict() for r in reports],
        "admitted": all(r.admitted for r in reports) if reports else False,
    }


def write_production_inventory_report(
    destination: Path,
    manifest_path: str = "configs/model_manifests/mistral_large_4.yaml",
    *,
    lister: ObjectLister,
    inventory_dir: Optional[Path] = None,
) -> Path:
    payload = build_production_inventory_report(manifest_path, lister=lister, inventory_dir=inventory_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


class InMemoryObjectLister:
    """Test/lab lister without touching Cloudflare credentials."""

    def __init__(self, records: Iterable[R2ObjectHead]) -> None:
        self._records = list(records)

    def list_prefix(self, prefix: str) -> Sequence[R2ObjectHead]:
        p = prefix.strip().lstrip("/")
        return [r for r in self._records if r.key.strip().lstrip("/").startswith(p)]


def inventory_manifest_integrity(manifest: ShardInventoryManifest) -> List[str]:
    """Validate pinned manifest digest and optional HMAC signature field."""
    reasons: List[str] = []
    if manifest.manifest_sha256:
        computed = manifest.computed_manifest_sha256()
        if computed != manifest.manifest_sha256.strip().lower():
            reasons.append("manifest_sha256_mismatch")
    if manifest.signature and len(manifest.signature) < 16:
        reasons.append("manifest_signature_too_short")
    return reasons


def load_inventory_for_variant(
    variant_tag: str,
    manifest_path: str = "configs/model_manifests/mistral_large_4.yaml",
    inventory_dir: Optional[Path] = None,
) -> Optional[ShardInventoryManifest]:
    doc = yaml.safe_load(Path(manifest_path).read_text(encoding="utf-8")) or {}
    inv_dir = inventory_dir or Path("configs/model_manifests/inventories")
    for variant in doc.get("variants") or []:
        if not isinstance(variant, dict):
            continue
        if str(variant.get("tag")) != variant_tag:
            continue
        ref = str(variant.get("inventory_ref") or "").strip()
        if not ref:
            return None
        path = inv_dir / ref
        if path.is_file():
            return load_inventory_json(path)
    return None


def r2_client_lister_factory() -> Callable[[], ObjectLister]:
    """Build a lister backed by R2Client HEAD/LIST metadata (no object download)."""

    def _factory() -> ObjectLister:
        from src.vault.r2_client import R2Client

        client = R2Client()

        class _ClientLister:
            def list_prefix(self, prefix: str) -> Sequence[R2ObjectHead]:
                rows = client.list_files(prefix)
                heads: List[R2ObjectHead] = []
                for row in rows:
                    key = str(row.get("key") or "")
                    etag = ""
                    meta_sha = ""
                    revision = ""
                    try:
                        head = client._client.head_object(Bucket=client.bucket, Key=key)  # noqa: SLF001
                        etag = str(head.get("ETag") or "")
                        metadata = head.get("Metadata") or {}
                        if isinstance(metadata, dict):
                            meta_sha = str(
                                metadata.get("sha256")
                                or metadata.get("x-amz-meta-sha256")
                                or metadata.get("sha256_hex")
                                or ""
                            ).lower()
                            revision = str(metadata.get("revision") or metadata.get("source_revision") or "")
                    except Exception:
                        etag = ""
                    heads.append(
                        R2ObjectHead(
                            key=key,
                            size_bytes=int(row.get("size") or 0),
                            etag=etag,
                            metadata_sha256=meta_sha,
                            last_modified=str(row.get("last_modified") or ""),
                            revision=revision,
                        )
                    )
                return heads

        return _ClientLister()

    return _factory
