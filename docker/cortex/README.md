# Cortex customer-tier container images

Three deployment tiers ship under `S3M_BUILD_PROFILE=customer`:

| Tier | Dockerfile | Platform | Role |
|------|------------|----------|------|
| core | `Dockerfile.core` | linux/amd64 | Full command CPU footprint |
| regional | `Dockerfile.regional` | linux/amd64 | Theater / coalition node |
| edge | `Dockerfile.edge` | linux/arm64 (Jetson) | Disconnected tactical edge |

## Build

Always exclude offensive cyber modules from the build context:

```bash
docker build -f docker/cortex/Dockerfile.core \
  --ignorefile docker/cortex/customer.dockerignore \
  -t cortex-core:local .

docker buildx build --platform linux/arm64 \
  -f docker/cortex/Dockerfile.edge \
  --ignorefile docker/cortex/customer.dockerignore \
  -t cortex-edge:local .
```

Images run as UID `10001` with a read-only root when started with `docker run --read-only` and writable volumes on `/opt/s3m/data`, `/opt/s3m/run`, and `/tmp`.

## Offline updates

Signed bundles are produced with `scripts/cortex/build_bundle.py` and verified in the field with `scripts/cortex/verify_bundle.py` against customer-pinned cosign public keys (PKCS#11 HSM private keys via `COSIGN_PKCS11_*` at sign time).
