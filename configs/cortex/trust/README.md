# Pinned cosign public keys

Place customer-approved `*.pub` files in this directory on operational systems (e.g. `/etc/s3m/cortex/trust`). `scripts/cortex/verify_bundle.py` loads only these keys and rejects bundles signed elsewhere.

CI generates `ci-test.pub` at build time; do not deploy that key outside test environments.
