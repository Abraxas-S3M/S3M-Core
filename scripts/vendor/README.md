# S3M Vendor Vault Seeding

This directory manages external GitHub vendor code ingestion for the S3M sovereign vault.

Military/tactical context: vendor dependencies are staged into Cloudflare R2 so field systems can rebuild software stacks offline without live internet access.

## Files

- `build_repos_manifest.py` — scans `packages/integrations/*/*/manifest.yaml` and generates `repos.txt`.
- `repos.txt` — canonical clone list consumed by Hetzner seeding.
- `clone_all.sh` — bounded-disk clone/upload pipeline with resume markers.

## Run on Hetzner

```bash
bash scripts/vendor/clone_all.sh
```

Common options:

```bash
bash scripts/vendor/clone_all.sh --parallel 4
bash scripts/vendor/clone_all.sh --domain cyber
bash scripts/vendor/clone_all.sh --dry-run
```

## Regenerate `repos.txt`

After adding or editing integration wrappers:

```bash
python scripts/vendor/build_repos_manifest.py
```

For local testing output:

```bash
python scripts/vendor/build_repos_manifest.py --output /tmp/test-repos.txt
```

## Failure handling and resume

- `clone_all.sh` checks for `vendor/{domain}/{slug}/.cloned` marker in object storage before cloning.
- If marker exists, repo is skipped.
- If a clone/upload fails, the script logs `FAIL` and continues.
- Re-running the same command resumes from remaining repositories.

## Runtime and disk profile

- Runtime depends on internet/object storage throughput and number of repos.
- Local disk usage is bounded to one cloned repository per worker.
- With `--parallel N`, each worker still processes repos one-at-a-time in its own `/tmp/s3m-vendor/...` path.

## Cloudflare R2 destination layout

- Source files: `vendor/{domain}/{slug}/...`
- Completion marker: `vendor/{domain}/{slug}/.cloned`

