# Core-tier vLLM strategist (reference deployment)

Tactical context: hosts the 1T-class sparse MoE **strategist** on a multi-GPU
server inside the classified enclave. S3M edge nodes call it over **mTLS** on a
private address using the `vllm` inference backend—no public internet inference.

## Prerequisites

- NVIDIA data-center GPUs with sufficient aggregate VRAM for your sharded checkpoint
- vLLM installed in a dedicated Python 3.11 virtual environment on the core node
- Model weights on local NVMe (`MODEL_PATH` placeholder below—**not included**)
- mTLS client/server certificates issued by your PKI and registered in the S3M vault
- Attestation endpoint exposing confidential-computing evidence (TDX / SEV-SNP / NVIDIA CC)

## Example launch command

```bash
export MODEL_PATH="/var/lib/s3m/weights/STRATEGIST_MOE_PLACEHOLDER"
export VLLM_HOST="0.0.0.0"
export VLLM_PORT="8000"

# Placeholder: replace tensor-parallel / pipeline-parallel sizes for your rack.
python -m vllm.entrypoints.openai.api_server \
  --model "${MODEL_PATH}" \
  --host "${VLLM_HOST}" \
  --port "${VLLM_PORT}" \
  --tensor-parallel-size 8 \
  --trust-remote-code \
  --served-model-name strategist-moe
```

Enable HTTPS termination and client certificate validation at the reverse proxy
or vLLM TLS front-end; map vault paths into S3M `VllmBackend` config
(`vault_mtls_paths`).

## systemd

Install the reference unit:

```bash
sudo cp deploy/core/vllm/s3m-vllm-strategist.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now s3m-vllm-strategist.service
```

Edit `Environment=MODEL_PATH=...` in the unit file before enable.

## S3M backend configuration sketch

```yaml
runtime_format: vllm
model_path: strategist-moe
base_url: https://vllm-strategist.internal:8443
lab_mode: false
vault_mtls_paths:
  client_cert: kv/tactical/vllm/client-cert
  client_key: kv/tactical/vllm/client-key
  ca_cert: kv/tactical/vllm/ca-cert
cortex_config_path: configs/cortex.yaml
task_type: strategist
max_output_tokens_by_task:
  strategist: 4096
```

## Health and attestation

- Health: `GET /health` (or override `health_path`)
- Attestation: `GET /v1/attestation` returning an opaque evidence blob

S3M refuses to load the backend in production until attestation verifies.
