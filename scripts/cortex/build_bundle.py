#!/usr/bin/env python3
"""Assemble cortex-update-<version>.tar with images, SBOMs, signatures, and signed index."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, List

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.cortex.bundle_common import (  # noqa: E402
    INDEX_NAME,
    INDEX_SIG_NAME,
    BundleArtifact,
    build_index,
    expected_signature_path,
    sha256_file,
    write_index,
)
from scripts.cortex.cbom import build_cbom  # noqa: E402
from scripts.cortex.signing import sign_blob, slsa_provenance_stub  # noqa: E402
from scripts.cortex.sbom import build_sbom_from_requirements, syft_sbom, tier_requirements  # noqa: E402


def _docker_save(image: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["docker", "save", "-o", str(dest), image], check=True)


def _stub_image_tar(dest: Path, tier: str, version: str) -> None:
    """Placeholder image blob for lightweight CI when docker save is not required."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"tier": tier, "version": version, "stub": True}).encode("utf-8")
    dest.write_bytes(payload)


def _sign_tree(root: Path, private_key: Path, rel_paths: List[str]) -> None:
    for rel in rel_paths:
        target = root / rel
        sig = root / expected_signature_path(rel)
        sign_blob(target, sig, private_key=private_key)


def assemble(args: argparse.Namespace) -> Path:
    repo = Path(args.repo_root).resolve()
    version = args.version
    tiers = ["core", "regional", "edge"]

    with tempfile.TemporaryDirectory(prefix="cortex-bundle-") as tmp:
        stage = Path(tmp)
        artifacts: List[BundleArtifact] = []

        image_refs: Dict[str, str] = {
            "core": args.image_core,
            "regional": args.image_regional,
            "edge": args.image_edge,
        }

        for tier in tiers:
            image_rel = f"images/{tier}/image.tar"
            image_path = stage / image_rel
            if args.stub_images:
                _stub_image_tar(image_path, tier, version)
            else:
                _docker_save(image_refs[tier], image_path)
            artifacts.append(
                BundleArtifact(
                    path=image_rel,
                    sha256=sha256_file(image_path),
                    kind="image",
                    tier=tier,
                )
            )

            sbom_rel = f"sbom/{tier}.cdx.json"
            sbom_path = stage / sbom_rel
            sbom_path.parent.mkdir(parents=True, exist_ok=True)
            if args.stub_images:
                sbom = build_sbom_from_requirements(tier, tier_requirements(tier), image_refs[tier])
                sbom_path.write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
            elif not syft_sbom(image_refs[tier], sbom_path):
                sbom = build_sbom_from_requirements(tier, tier_requirements(tier), image_refs[tier])
                sbom_path.write_text(json.dumps(sbom, indent=2) + "\n", encoding="utf-8")
            artifacts.append(BundleArtifact(path=sbom_rel, sha256=sha256_file(sbom_path), kind="sbom", tier=tier))

            prov_rel = f"attestations/{tier}.slsa.json"
            prov_path = stage / prov_rel
            prov_path.parent.mkdir(parents=True, exist_ok=True)
            slsa_provenance_stub(image_refs[tier], prov_path)
            artifacts.append(
                BundleArtifact(path=prov_rel, sha256=sha256_file(prov_path), kind="attestation", tier=tier)
            )

        cbom_rel = "cbom/cortex-cbom.json"
        cbom_path = stage / cbom_rel
        cbom_path.parent.mkdir(parents=True, exist_ok=True)
        cbom_path.write_text(
            json.dumps(build_cbom(repo / "configs/cortex/cbom_inventory.yaml", version), indent=2) + "\n",
            encoding="utf-8",
        )
        artifacts.append(BundleArtifact(path=cbom_rel, sha256=sha256_file(cbom_path), kind="cbom"))

        manifest_src = repo / "configs" / "model_manifests"
        if manifest_src.is_dir():
            for mf in sorted(manifest_src.glob("*.y*ml")):
                rel = f"model-manifests/{mf.name}"
                dest = stage / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(mf, dest)
                artifacts.append(
                    BundleArtifact(path=rel, sha256=sha256_file(dest), kind="model_manifest")
                )

        index_path = stage / INDEX_NAME
        write_index(build_index(version, artifacts), index_path)

        sign_paths = [a.path for a in artifacts]
        _sign_tree(stage, args.private_key, sign_paths)

        index_sig = stage / INDEX_SIG_NAME
        sign_blob(index_path, index_sig, private_key=args.private_key)

        bundle_name = f"cortex-update-{version}.tar"
        bundle_out = Path(args.output).resolve()
        bundle_out.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(bundle_out, "w") as archive:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=str(path.relative_to(stage)))
        return bundle_out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build signed Cortex offline update bundle.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", required=True, help="Output tar path.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--image-core", default="cortex-core:ci")
    parser.add_argument("--image-regional", default="cortex-regional:ci")
    parser.add_argument("--image-edge", default="cortex-edge:ci")
    parser.add_argument(
        "--stub-images",
        action="store_true",
        help="Skip docker save; write stub image blobs.",
    )
    args = parser.parse_args()
    out = assemble(args)
    print(f"Wrote bundle: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
