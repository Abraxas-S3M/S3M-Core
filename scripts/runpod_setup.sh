#!/usr/bin/env bash
# S3M RunPod Pod Setup Script
# Run this on a fresh RunPod 4090 pod to bootstrap the training environment.
#
# Usage: curl -sSL https://raw.githubusercontent.com/Abraxas-S3M/S3M-Core/main/scripts/runpod_setup.sh | bash

set -euo pipefail

echo "════════════════════════════════════════════════════════"
echo "  S3M — Sovereign Saudi Strategic Model"
echo "  RunPod RTX 4090 Training Environment Setup"
echo "  UNCLASSIFIED - FOUO"
echo "════════════════════════════════════════════════════════"

WORKSPACE="/workspace/s3m"

# 1. Clone repo
echo "[1/7] Cloning S3M-Core..."
if [ ! -d "$WORKSPACE" ]; then
    git clone https://github.com/Abraxas-S3M/S3M-Core.git "$WORKSPACE"
else
    cd "$WORKSPACE" && git pull
fi
cd "$WORKSPACE"

# 2. Install GPU training deps
echo "[2/7] Installing GPU training dependencies..."
pip install --no-cache-dir -r requirements-gpu-training.txt

# 3. Install Flash Attention 2
echo "[3/7] Installing Flash Attention 2..."
pip install --no-cache-dir flash-attn --no-build-isolation 2>/dev/null || echo "Flash Attention install failed (non-fatal)"

# 4. Install Unsloth
echo "[4/7] Installing Unsloth..."
pip install --no-cache-dir "unsloth[cu124-torch230] @ git+https://github.com/unslothai/unsloth.git" 2>/dev/null || echo "Unsloth install failed (non-fatal)"

# 5. Build llama.cpp (for GGUF export)
echo "[5/7] Building llama.cpp..."
if [ ! -d "/workspace/llama.cpp" ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git /workspace/llama.cpp
    cd /workspace/llama.cpp
    cmake -B build -DGGML_CUDA=ON
    cmake --build build --config Release -j "$(nproc)"
    cd "$WORKSPACE"
fi

# 6. Create directories
echo "[6/7] Creating training directories..."
mkdir -p data/datasets data/eval checkpoints/gpu models/merged models/gguf
mkdir -p state/training/job_queue/{pending,running,completed,failed,promoted}

# 7. Verify GPU
echo "[7/7] Verifying GPU..."
python3 -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'VRAM: {torch.cuda.get_device_properties(0).total_mem / 1024**3:.1f} GB')
try:
    import unsloth; print('Unsloth: installed')
except: print('Unsloth: not available')
try:
    import flash_attn; print('Flash Attention: installed')
except: print('Flash Attention: not available')
try:
    import bitsandbytes; print('bitsandbytes: installed')
except: print('bitsandbytes: not available')
"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  S3M RunPod setup complete!"
echo ""
echo "  Quick start:"
echo "    python scripts/train_gpu.py --engine phi3 --dataset data/datasets/s3m_phi3_instruct.jsonl"
echo "    python scripts/train_gpu.py --engine allam --dataset data/datasets/s3m_allam_bilingual.jsonl"
echo ""
echo "  GPU worker (polls job queue):"
echo "    python scripts/gpu_worker.py --poll-interval 30"
echo "════════════════════════════════════════════════════════"
