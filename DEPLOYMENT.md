# S3M Cloud CPU Deployment Guide — Hetzner + Cloudflare Pages

## Architecture
Users
↓
demo.yourdomain.com → Cloudflare Pages → static React/Vite GUI
↓ API calls / WebSocket
api.yourdomain.com → Cloudflare DNS → Hetzner server
├─ s3m-api container    (FastAPI, port 8080)
├─ s3m-worker container (training, checkpointing)
└─ mounted persistent volumes (data, models)

## Prerequisites

- Hetzner Cloud server (CPX41 recommended: 8 vCPU, 16 GB RAM, 240 GB disk)
- Domain with Cloudflare DNS
- Docker + Docker Compose installed on Hetzner server
- SSH access to Hetzner server

## Step 1 — Provision Hetzner Server
```bash
# After creating CPX41 via Hetzner console:
ssh root@YOUR_HETZNER_IP

# Install Docker
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin

# Create app directory
mkdir -p /opt/s3m && cd /opt/s3m
```

## Step 2 — Clone and Configure
```bash
git clone https://github.com/Abraxas-S3M/S3M-Core.git /opt/s3m
cd /opt/s3m

# Create environment file (NEVER committed to git)
cp .env.cloud.example .env.cloud
nano .env.cloud  # Set real API key, CORS origins, domain
```

## Step 3 — Build and Launch
```bash
# Build CPU images
docker compose -f docker/docker-compose.cloud.yml build

# Start services
docker compose -f docker/docker-compose.cloud.yml up -d

# Verify
curl http://localhost:8080/health
docker compose -f docker/docker-compose.cloud.yml logs -f
```

## Step 4 — Cloudflare DNS

1. Add an A record: `api.yourdomain.com → YOUR_HETZNER_IP` (proxied)
2. In Cloudflare SSL/TLS → set mode to "Full (Strict)"
3. Verify: `curl https://api.yourdomain.com/health`

## Step 5 — Readiness Validation
```bash
# All three must return 200:
curl -s https://api.yourdomain.com/health | jq .
curl -s https://api.yourdomain.com/api/v1/workspaces/command/operational-context | jq .

# WebSocket check (requires wscat):
wscat -c wss://api.yourdomain.com/ws
```

## Operations

### View Logs
```bash
docker compose -f docker/docker-compose.cloud.yml logs -f s3m-api
docker compose -f docker/docker-compose.cloud.yml logs -f s3m-worker
```

### Restart
```bash
docker compose -f docker/docker-compose.cloud.yml restart
```

### Update Code
```bash
cd /opt/s3m
git pull
docker compose -f docker/docker-compose.cloud.yml build
docker compose -f docker/docker-compose.cloud.yml up -d
```

### Backup Persistent State
```bash
docker compose -f docker/docker-compose.cloud.yml stop
tar czf s3m-backup-$(date +%Y%m%d).tar.gz \
  /var/lib/docker/volumes/s3m-core_s3m-data \
  /var/lib/docker/volumes/s3m-core_s3m-models
docker compose -f docker/docker-compose.cloud.yml up -d
```

## Environment Variables Reference

| Variable | Default | Description |
|----------|---------|-------------|
| DEPLOYMENT_MODE | jetson_edge | `jetson_edge`, `cloud_cpu_demo`, `gpu_cluster` |
| S3M_DEVICE | auto | `cpu`, `cuda`, `auto` |
| S3M_HOST | 0.0.0.0 | Bind address |
| S3M_PORT | 8080 | API port |
| S3M_WORKERS | 1 | Uvicorn workers |
| S3M_API_KEY | (none) | API authentication key |
| S3M_AUTH_ENABLED | false | Enable API key auth |
| CORS_ORIGINS | * | Comma-separated allowed origins |
| S3M_LOG_LEVEL | info | Logging level |
| OMP_NUM_THREADS | 8 | OpenMP thread count |
| S3M_WORKER_INTERVAL_SECONDS | 300 | Worker sleep between cycles |
