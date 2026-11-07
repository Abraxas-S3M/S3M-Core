"""Shared types for Cortex offline update bundles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List


BUNDLE_FORMAT = "cortex-update-v1"
INDEX_NAME = "manifest/index.json"
INDEX_SIG_NAME = "manifest/index.json.sig"


@dataclass(frozen=True)
class BundleArtifact:
    path: str
    sha256: str
    kind: str
    tier: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "path": self.path,
            "sha256": self.sha256,
            "kind": self.kind,
        }
        if self.tier:
            payload["tier"] = self.tier
        return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_index(cortex_version: str, artifacts: List[BundleArtifact]) -> Dict[str, Any]:
    return {
        "bundle_format": BUNDLE_FORMAT,
        "cortex_version": cortex_version,
        "artifacts": [a.to_dict() for a in artifacts],
    }


def write_index(index: Dict[str, Any], dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def expected_signature_path(artifact_path: str) -> str:
    return f"{artifact_path}.sig"
