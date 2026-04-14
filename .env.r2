# S3M Cloudflare R2 Credentials
# UNCLASSIFIED - FOUO
# Shared by ALL tiers: Hetzner CCX33, RunPod 4090, local dev
# Generate at: Cloudflare Dashboard → R2 → Manage R2 API Tokens

# Cloudflare Account ID (from your dashboard URL)
S3M_CF_ACCOUNT_ID=CHANGEME

# R2 API Token — Permission: Object Read & Write, Scope: s3m-vault bucket
S3M_STORAGE_ACCESS_KEY=CHANGEME
S3M_STORAGE_SECRET_KEY=CHANGEME

# Derived endpoint (boto3 uses this directly)
S3M_STORAGE_ENDPOINT=https://${S3M_CF_ACCOUNT_ID}.r2.cloudflarestorage.com
S3M_STORAGE_BUCKET_NAME=s3m-vault

# Legacy aliases for backward compatibility
S3M_R2_ACCESS_KEY_ID=${S3M_STORAGE_ACCESS_KEY}
S3M_R2_SECRET_ACCESS_KEY=${S3M_STORAGE_SECRET_KEY}

# RunPod API (for Hetzner orchestrator to spin up GPU pods)
RUNPOD_API_KEY=CHANGEME

# Optional: W&B for experiment tracking
WANDB_API_KEY=
WANDB_PROJECT=s3m-training
