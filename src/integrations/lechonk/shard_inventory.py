"""Multi-shard weight inventory verification for Le Chonk admission (fail-closed)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set


@dataclass(frozen=True)
class ShardRecord:
    """One artifact file in a multi-shard checkpoint."""

    relative_path: str
    size_bytes: int
    sha256: str

    def normalized_path(self) -> str:
        return self.relative_path.replace("\\", "/").lstrip("/")


@dataclass(frozen=True)
class ShardInventoryManifest:
    """Signed or pinned inventory describing every expected shard."""

    variant_tag: str
    model_id: str
    source_revision: str
    shards: tuple[ShardRecord, ...]
    manifest_sha256: str = ""
    signature: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ShardInventoryManifest:
        variant = str(data.get("variant_tag") or data.get("tag") or "")
        model_id = str(data.get("model_id") or "")
        revision = str(data.get("source_revision") or "")
        manifest_digest = str(data.get("manifest_sha256") or "").strip().lower()
        signature = str(data.get("signature") or "")
        raw_shards = data.get("shards") or []
        shards: List[ShardRecord] = []
        if isinstance(raw_shards, list):
            for item in raw_shards:
                if not isinstance(item, dict):
                    continue
                rel = str(item.get("relative_path") or item.get("path") or "").strip()
                if not rel:
                    continue
                size = int(item.get("size_bytes") or item.get("size") or 0)
                digest = str(item.get("sha256") or "").strip().lower()
                shards.append(ShardRecord(relative_path=rel, size_bytes=size, sha256=digest))
        return cls(
            variant_tag=variant,
            model_id=model_id,
            source_revision=revision,
            shards=tuple(shards),
            manifest_sha256=manifest_digest,
            signature=signature,
        )

    def expected_paths(self) -> Set[str]:
        return {s.normalized_path() for s in self.shards}

    def canonical_bytes(self) -> bytes:
        payload = {
            "model_id": self.model_id,
            "variant_tag": self.variant_tag,
            "source_revision": self.source_revision,
            "shards": [
                {
                    "relative_path": s.normalized_path(),
                    "size_bytes": s.size_bytes,
                    "sha256": s.sha256,
                }
                for s in sorted(self.shards, key=lambda x: x.normalized_path())
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def computed_manifest_sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass
class ShardVerificationResult:
    variant_tag: str
    admitted: bool
    reasons: List[str] = field(default_factory=list)
    verified_count: int = 0
    expected_count: int = 0

    def explanation(self) -> str:
        if self.admitted:
            return f"admitted:{self.verified_count}/{self.expected_count}"
        return "; ".join(self.reasons) if self.reasons else "rejected"


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _iter_artifact_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def verify_shard_inventory(
    manifest: ShardInventoryManifest,
    artifact_root: Path,
    *,
    allow_extra_files: bool = False,
) -> ShardVerificationResult:
    """
    Fail-closed verification: missing hash, unknown file, size or digest mismatch rejects admission.
    """
    reasons: List[str] = []
    root = artifact_root.resolve()
    if not manifest.shards:
        reasons.append("empty_shard_inventory")
        return ShardVerificationResult(
            variant_tag=manifest.variant_tag,
            admitted=False,
            reasons=reasons,
            expected_count=0,
        )

    if manifest.manifest_sha256:
        computed = manifest.computed_manifest_sha256()
        if computed != manifest.manifest_sha256.strip().lower():
            reasons.append("manifest_sha256_mismatch")

    expected = {s.normalized_path(): s for s in manifest.shards}
    on_disk: Dict[str, Path] = {}
    for path in _iter_artifact_files(root):
        rel = path.relative_to(root).as_posix()
        on_disk[rel] = path

    if not allow_extra_files:
        extra = set(on_disk.keys()) - set(expected.keys())
        if extra:
            reasons.append(f"unexpected_files:{len(extra)}")

    missing = set(expected.keys()) - set(on_disk.keys())
    if missing:
        reasons.append(f"missing_shards:{len(missing)}")

    verified = 0
    for rel, record in expected.items():
        path = on_disk.get(rel)
        if path is None:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            reasons.append(f"unreadable:{rel}")
            continue
        if record.size_bytes and size != record.size_bytes:
            reasons.append(f"size_mismatch:{rel}")
            continue
        if not record.sha256 or len(record.sha256) != 64:
            reasons.append(f"absent_hash:{rel}")
            continue
        measured = _sha256_file(path)
        if measured != record.sha256:
            reasons.append(f"sha256_mismatch:{rel}")
            continue
        verified += 1

    admitted = len(reasons) == 0 and verified == len(expected)
    return ShardVerificationResult(
        variant_tag=manifest.variant_tag,
        admitted=admitted,
        reasons=reasons,
        verified_count=verified,
        expected_count=len(expected),
    )


def load_inventory_json(path: Path) -> ShardInventoryManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("inventory document must be a JSON object")
    return ShardInventoryManifest.from_mapping(data)


def merge_variant_inventories(
    manifest_doc: Mapping[str, Any],
    inventory_dir: Optional[Path] = None,
) -> Dict[str, ShardInventoryManifest]:
    """Load per-variant inventories referenced from the Le Chonk YAML manifest."""
    inv_root = inventory_dir or Path("configs/model_manifests/inventories")
    variants = manifest_doc.get("variants") or []
    by_tag: Dict[str, ShardInventoryManifest] = {}
    if not isinstance(variants, list):
        return by_tag
    for variant in variants:
        if not isinstance(variant, dict):
            continue
        tag = str(variant.get("tag") or "")
        inv_ref = str(variant.get("inventory_ref") or "").strip()
        if not tag or not inv_ref:
            continue
        inv_path = inv_root / inv_ref
        if not inv_path.is_file():
            continue
        inv = load_inventory_json(inv_path)
        by_tag[tag] = inv
    return by_tag
