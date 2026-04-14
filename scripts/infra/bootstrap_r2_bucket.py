#!/usr/bin/env python3
"""Bootstrap Cloudflare R2 bucket with vault structure and verify connectivity.

Run once during initial setup before seeding models or deploying workers.
Usage: python scripts/infra/bootstrap_r2_bucket.py
       python scripts/infra/bootstrap_r2_bucket.py --verify-only
       python scripts/infra/bootstrap_r2_bucket.py --instructions
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.object_storage import ObjectStorageConnector

LOGGER = logging.getLogger("s3m.infra.bootstrap_r2")

VAULT_DIRECTORIES = [
    "models/fp16/",
    "models/q4-gguf/",
    "models/fp16-adapters/",
    "models/fp16-merged/",
    "datasets/saudi_mod/scenarios/",
    "datasets/ukraine_mod/scenarios/",
    "datasets/nato/scenarios/",
    "datasets/pseudo/",
    "datasets/training-data/",
    "checkpoints/hetzner/",
    "checkpoints/runpod/",
    "eval-results/",
    "grok-verdicts/pending/",
    "grok-verdicts/approved/",
    "grok-verdicts/rejected/",
    "gui-snapshots/",
    "manifests/",
    "vendor/",
]


def verify_connectivity(connector: ObjectStorageConnector) -> bool:
    """Round-trip write/read/delete test against R2."""
    test_key = "_s3m_connectivity_test"
    test_payload = b"S3M R2 connectivity verification"
    try:
        connector.put_bytes(test_key, test_payload)
        retrieved = connector.get_bytes(test_key)
        connector.delete_file(test_key)
        if retrieved == test_payload:
            LOGGER.info("R2 connectivity verified: round-trip OK")
            return True
        LOGGER.error("R2 round-trip data mismatch")
        return False
    except Exception as exc:
        LOGGER.error("R2 connectivity failed: %s", exc)
        return False


def bootstrap_vault(connector: ObjectStorageConnector) -> dict[str, int]:
    """Create .keep sentinel files to establish vault directory structure."""
    created = 0
    skipped = 0
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for prefix in VAULT_DIRECTORIES:
        keep_key = f"{prefix}.keep"
        if connector.file_exists(keep_key):
            LOGGER.info("Exists: %s", keep_key)
            skipped += 1
            continue
        connector.put_bytes(
            keep_key,
            json.dumps({"created": ts, "purpose": "vault_structure"}).encode(),
            content_type="application/json",
        )
        LOGGER.info("Created: %s", keep_key)
        created += 1
    return {"created": created, "skipped": skipped}


def print_instructions() -> None:
    """Print Cloudflare R2 setup guide."""
    print("""
S3M CLOUDFLARE R2 SETUP
=======================

1. Cloudflare Dashboard → R2 Object Storage → Create bucket: s3m-vault

2. Create R2 API Token:
   Dashboard → R2 → Manage R2 API Tokens → Create
   Permission: Object Read & Write
   Scope: Apply to specific bucket → s3m-vault

3. Fill in .env.r2:
   S3M_CF_ACCOUNT_ID    = (from dashboard URL)
   S3M_STORAGE_ACCESS_KEY = (R2 token Access Key ID)
   S3M_STORAGE_SECRET_KEY = (R2 token Secret Access Key)

4. Set lifecycle rules (Dashboard → R2 → s3m-vault → Settings → Lifecycle):
   checkpoints/runpod/*            → Delete after 7 days
   checkpoints/hetzner/*           → Delete after 30 days
   grok-verdicts/rejected/*        → Delete after 7 days
   grok-verdicts/pending/*         → Delete after 3 days

5. Run this script:
   python scripts/infra/bootstrap_r2_bucket.py

6. Seed the vault:
   python scripts/storage/seed_vault.py --models --engine phi3 --engine mistral --engine allam
   python scripts/storage/seed_vault.py --datasets --priority

7. (Optional) Bind R2 to Cloudflare Pages:
   Pages → s3m-gui → Settings → Bindings → R2
   Variable name: S3M_VAULT  Bucket: s3m-vault

STORAGE PLAN: Start with 5 TB.
  Base weights:   554 GB (immutable)
  Datasets:     1,291 GB (seed once)
  Merged models:  810 GB (grows with training)
  Checkpoints:    607 GB (lifecycle-managed)
  Adapters:        30 GB
  Ops:             20 GB
  TOTAL:        3,312 GB → 5 TB plan at $75/mo
""")


def main() -> int:
    logging.basicConfig(level="INFO", format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Bootstrap S3M Cloudflare R2 vault")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--instructions", action="store_true")
    args = parser.parse_args()

    if args.instructions:
        print_instructions()
        return 0

    connector = ObjectStorageConnector()
    LOGGER.info("Connecting: endpoint=%s bucket=%s", connector.endpoint, connector.bucket_name)

    if not verify_connectivity(connector):
        LOGGER.error("FAILED — check .env.r2 credentials")
        print_instructions()
        return 1

    if args.verify_only:
        print("R2 connectivity OK")
        return 0

    result = bootstrap_vault(connector)
    LOGGER.info("Bootstrap complete: %s", result)
    print(f"Created {result['created']} directories, {result['skipped']} already existed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
