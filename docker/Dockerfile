# S3M Sovereign Military AI — Production Container
# Target: NVIDIA Jetson AGX Orin 64GB
# Base: NVIDIA L4T PyTorch (JetPack 6.x)
#
# Build: docker build -t s3m:latest -f docker/Dockerfile .
# Run:   docker run --runtime=nvidia --network=none -p 8080:8080 s3m:latest

# Stage 1: Base with CUDA/PyTorch
FROM nvcr.io/nvidia/l4t-pytorch:r36.2.0-pth2.1-py3 AS base

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip python3-dev build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/s3m

# Stage 2: Install Python dependencies
COPY requirements-all.txt .
RUN pip3 install --no-cache-dir -r requirements-all.txt \
    || pip3 install --no-cache-dir --break-system-packages -r requirements-all.txt

# Stage 3: Copy application
COPY src/ src/
COPY configs/ configs/
COPY scripts/ scripts/
COPY docs/ docs/
COPY architecture/ architecture/
COPY models/ models/ 2>/dev/null || true

# Create data directories
RUN mkdir -p data/threat_logs data/security_audit data/replays data/synthetic \
    data/manifests data/benchmarks data/osint data/decision_logs data/interop \
    data/security_reports models/policies models/optimized configs/keys

# Ensure no network access in production
# The --network=none flag in docker run enforces air-gap at container level

EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

# Entrypoint
ENV PYTHONPATH=/opt/s3m
CMD ["python3", "scripts/start_api.py"]
