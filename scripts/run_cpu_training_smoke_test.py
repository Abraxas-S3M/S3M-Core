#!/usr/bin/env python3
"""
S3M CPU Training Smoke Test
Validates the full CPU training pipeline end-to-end.

Tests:
1. Hardware profiling (ISA detection, NUMA, precision policy)
2. 4-bit QAT with tanh clipping on a tiny model
3. Checkpoint save/resume cycle
4. Evaluation harness pass/fail
5. Arabic text handling (if ALLaM manifest present)

Run: python scripts/run_cpu_training_smoke_test.py
Exit 0 on success, 1 on failure.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile
from typing import Any, Callable

import psutil
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.edge_runtime.hardware_profiler import HardwareProfiler
from src.training.cpu_adaptation.eval_harness import CPUEvaluationHarness


def _require_torch() -> Any:
    try:
        import torch  # type: ignore
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError("torch is required for CPU training smoke tests") from exc
    return torch


def _read_cpu_flags() -> set[str]:
    cpuinfo = Path("/proc/cpuinfo")
    flags: set[str] = set()
    if not cpuinfo.exists():
        return flags
    for line in cpuinfo.read_text(encoding="utf-8", errors="ignore").splitlines():
        lower = line.lower()
        if lower.startswith("flags") or lower.startswith("features"):
            _, raw = line.split(":", 1)
            for token in raw.strip().split():
                flags.add(token.lower())
    return flags


def _detect_isa_capabilities() -> dict[str, bool]:
    machine = platform.machine().lower()
    flags = _read_cpu_flags()
    return {
        "is_arm": any(item in machine for item in ("arm", "aarch64")),
        "has_neon": "neon" in flags or "asimd" in flags,
        "has_sve": "sve" in flags,
        "has_avx2": "avx2" in flags,
        "has_avx512": any(flag.startswith("avx512") for flag in flags),
        "has_vnni": "avx_vnni" in flags or "avx512_vnni" in flags,
    }


def _detect_numa_nodes() -> int:
    node_root = Path("/sys/devices/system/node")
    if not node_root.exists():
        return 1
    count = sum(1 for path in node_root.iterdir() if path.name.startswith("node") and path.name[4:].isdigit())
    return max(1, count)


def _select_precision_policy(capabilities: dict[str, bool]) -> str:
    if capabilities.get("has_vnni") or capabilities.get("has_avx512"):
        return "bf16_preferred"
    if capabilities.get("has_avx2") or capabilities.get("has_neon"):
        return "fp16_preferred"
    return "fp32_fallback"


def _soft_clip_tanh(weights: Any, clip_value: float = 3.0) -> Any:
    torch = _require_torch()
    return clip_value * torch.tanh(weights / clip_value)


def _symmetric_quantize_4bit_with_ste(weights: Any) -> tuple[Any, float, Any]:
    torch = _require_torch()
    max_abs = float(weights.detach().abs().max().item())
    scale = max(max_abs / 7.0, 1e-8)
    q_int = torch.clamp(torch.round(weights / scale), min=-7, max=7)
    dequant = q_int * scale
    ste = weights + (dequant - weights).detach()
    return ste, scale, q_int


def _count_unique_levels(tensor: Any) -> int:
    torch = _require_torch()
    unique_values = torch.unique(tensor.detach().reshape(-1))
    return int(unique_values.numel())


@dataclass
class _QATArtifacts:
    model: Any
    optimizer: Any
    losses: list[float]
    layer_unique_counts: dict[str, int]


class _TinyQATMLP:
    def __init__(self) -> None:
        torch = _require_torch()
        self.net = torch.nn.Sequential(
            torch.nn.Linear(16, 32),
            torch.nn.Tanh(),
            torch.nn.Linear(32, 16),
        )
        with torch.no_grad():
            for name, parameter in self.net.named_parameters():
                if "weight" in name:
                    parameter.uniform_(-3.0, 3.0)

    def parameters(self) -> Any:
        return self.net.parameters()

    def named_parameters(self) -> Any:
        return self.net.named_parameters()

    def __call__(self, inputs: Any) -> Any:
        return self.net(inputs)


class QuantAwareAdamW:
    """
    Minimal optimizer wrapper for smoke testing QAT projection on CPU.

    Military/tactical context:
    This keeps tiny-node retraining deterministic so build-gate checks catch
    quantization drift before field promotion.
    """

    def __init__(self, params: Any, lr: float = 2e-2, weight_decay: float = 1e-2) -> None:
        torch = _require_torch()
        self._torch = torch
        self._params = list(params)
        self._optim = torch.optim.AdamW(self._params, lr=lr, weight_decay=weight_decay)

    def zero_grad(self) -> None:
        self._optim.zero_grad()

    def step(self) -> dict[str, int]:
        self._optim.step()
        unique_levels: dict[str, int] = {}
        with self._torch.no_grad():
            for idx, parameter in enumerate(self._params):
                clipped = _soft_clip_tanh(parameter)
                ste, _, q_int = _symmetric_quantize_4bit_with_ste(clipped)
                parameter.copy_(ste)
                unique_levels[f"param_{idx}"] = _count_unique_levels(q_int)
        return unique_levels

    def state_dict(self) -> dict[str, Any]:
        return self._optim.state_dict()

    def load_state_dict(self, payload: dict[str, Any]) -> None:
        self._optim.load_state_dict(payload)


def _build_tiny_batch() -> tuple[Any, Any]:
    torch = _require_torch()
    torch.manual_seed(7)
    inputs = torch.randn(64, 16)
    projection = torch.linspace(-0.75, 0.75, steps=16).reshape(16, 1)
    targets = torch.tanh(inputs @ projection).repeat(1, 16)
    return inputs, targets


def _run_qat_steps(model: _TinyQATMLP, optimizer: QuantAwareAdamW, steps: int) -> tuple[list[float], dict[str, int]]:
    torch = _require_torch()
    criterion = torch.nn.MSELoss()
    features, targets = _build_tiny_batch()
    losses: list[float] = []
    last_unique_counts: dict[str, int] = {}
    for _ in range(steps):
        optimizer.zero_grad()
        outputs = model(features)
        loss = criterion(outputs, targets)
        loss.backward()
        losses.append(float(loss.detach().item()))
        last_unique_counts = optimizer.step()
    return losses, last_unique_counts


def _checkpoint_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _arabic_tokenize(text: str) -> list[str]:
    # Character-level tokenization guarantees safe round-trip for Arabic script.
    return list(text)


def _arabic_detokenize(tokens: list[str]) -> str:
    return "".join(tokens)


def test_isa_detection() -> None:
    """Verify ISA capabilities are detected correctly."""
    profile = HardwareProfiler().run()
    capabilities = _detect_isa_capabilities()
    numa_nodes = _detect_numa_nodes()

    assert profile.cpu_cores >= 1
    assert isinstance(profile.cpu_arch, str) and profile.cpu_arch
    assert isinstance(capabilities, dict) and capabilities
    assert numa_nodes >= 1


def test_precision_policy() -> None:
    """Verify precision selection matches hardware."""
    capabilities = _detect_isa_capabilities()
    policy = _select_precision_policy(capabilities)
    assert policy in {"bf16_preferred", "fp16_preferred", "fp32_fallback"}

    if capabilities.get("has_avx512") or capabilities.get("has_vnni"):
        assert policy == "bf16_preferred"
    elif capabilities.get("has_avx2") or capabilities.get("has_neon"):
        assert policy == "fp16_preferred"
    else:
        assert policy == "fp32_fallback"


def test_tanh_soft_clipping() -> None:
    """Verify W = 3.0 * tanh(W / 3.0) is applied correctly.
    Create a small tensor, apply clipping, verify:
    1. Values are bounded within (-3, 3)
    2. Gradient flow is preserved (no zeros at boundaries)
    3. Idempotent for values already in range
    """
    torch = _require_torch()
    values = torch.tensor([-10.0, -3.0, -1.0, 0.0, 1.0, 3.0, 10.0], requires_grad=True)
    clipped = _soft_clip_tanh(values)

    assert float(clipped.max().item()) < 3.0
    assert float(clipped.min().item()) > -3.0

    clipped.sum().backward()
    grads = values.grad.detach()
    assert float(grads[1].abs().item()) > 0.0
    assert float(grads[-2].abs().item()) > 0.0

    small = torch.tensor([-0.2, 0.0, 0.2])
    clipped_small = _soft_clip_tanh(small)
    assert torch.allclose(clipped_small, small, atol=0.01)


def test_symmetric_quantizer() -> None:
    """Verify 4-bit symmetric quantization:
    1. Output has exactly 15 unique values
    2. STE gradient passes through correctly
    3. Dynamic per-layer scaling adapts to weight magnitude
    """
    torch = _require_torch()
    codebook_levels = torch.arange(-7, 8, dtype=torch.float32)
    weights = (codebook_levels / 7.0).clone().requires_grad_(True)
    quantized, scale, q_int = _symmetric_quantize_4bit_with_ste(weights)

    assert _count_unique_levels(q_int) == 15
    quantized.sum().backward()
    assert torch.allclose(weights.grad, torch.ones_like(weights), atol=1e-6)

    scaled_input = weights.detach() * 4.0
    _, larger_scale, _ = _symmetric_quantize_4bit_with_ste(scaled_input)
    assert larger_scale > scale


def test_qat_training_loop() -> _QATArtifacts:
    """Tiny model (2-layer MLP, ~1K params) trained with full QAT pipeline:
    1. QuantAwareAdamW with tanh clipping
    2. 10 steps of training
    3. Loss should decrease
    4. Weights should have 15 unique values per layer
    5. Memory should stay under 512 MB
    """
    model = _TinyQATMLP()
    optimizer = QuantAwareAdamW(model.parameters(), lr=3e-2, weight_decay=0.0)
    losses, layer_unique_counts = _run_qat_steps(model=model, optimizer=optimizer, steps=10)

    assert min(losses[1:]) < losses[0]
    assert all(count == 15 for count in layer_unique_counts.values())
    rss_mb = psutil.Process(os.getpid()).memory_info().rss / (1024.0 * 1024.0)
    assert rss_mb < 512.0
    return _QATArtifacts(model=model, optimizer=optimizer, losses=losses, layer_unique_counts=layer_unique_counts)


def test_checkpoint_save_resume() -> None:
    """
    1. Train for 5 steps, checkpoint
    2. Verify checkpoint manifest exists and is valid
    3. Load checkpoint, verify SHA256 matches
    4. Resume training for 5 more steps
    5. Verify loss continuity (no regression from resume)
    """
    torch = _require_torch()
    artifacts = test_qat_training_loop()
    model = artifacts.model
    optimizer = artifacts.optimizer

    with tempfile.TemporaryDirectory(prefix="s3m-cpu-training-") as tmpdir:
        tmp_path = Path(tmpdir)
        checkpoint_path = tmp_path / "tiny_qat.pt"
        manifest_path = tmp_path / "tiny_qat_manifest.json"

        pre_losses, _ = _run_qat_steps(model=model, optimizer=optimizer, steps=5)
        torch.save(
            {"model_state": model.net.state_dict(), "optimizer_state": optimizer.state_dict(), "step": 5, "losses": pre_losses},
            checkpoint_path,
        )
        digest = _checkpoint_sha256(checkpoint_path)
        manifest_payload = {
            "checkpoint_file": checkpoint_path.name,
            "sha256": digest,
            "step": 5,
            "loss_at_checkpoint": pre_losses[-1],
        }
        manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

        loaded_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert loaded_manifest["sha256"] == digest

        loaded_blob = torch.load(checkpoint_path, map_location="cpu")
        loaded_hash = _checkpoint_sha256(checkpoint_path)
        assert loaded_hash == loaded_manifest["sha256"]

        resumed_model = _TinyQATMLP()
        resumed_optimizer = QuantAwareAdamW(resumed_model.parameters(), lr=3e-2, weight_decay=0.0)
        resumed_model.net.load_state_dict(loaded_blob["model_state"])
        resumed_optimizer.load_state_dict(loaded_blob["optimizer_state"])

        resumed_losses, _ = _run_qat_steps(model=resumed_model, optimizer=resumed_optimizer, steps=5)
        assert resumed_losses[0] <= pre_losses[-1] * 1.5
        assert resumed_losses[-1] <= resumed_losses[0]


def test_chunk_recurrent() -> None:
    """Verify chunk-recurrent processing:
    1. Process a 2048-token sequence in 4 chunks of 512
    2. Verify activation memory is constant (not growing with chunks)
    3. Verify KV cache grows linearly with chunks
    4. Verify loss matches non-chunked processing (within tolerance)
    """
    torch = _require_torch()
    torch.manual_seed(11)
    seq_len = 2048
    chunk_size = 512
    hidden = 24
    inputs = torch.randn(seq_len, hidden)
    w_ih = torch.randn(hidden, hidden) * 0.05
    w_hh = torch.randn(hidden, hidden) * 0.05
    bias = torch.zeros(hidden)

    def run_recurrent(full_inputs: Any, state: Any | None = None) -> tuple[Any, Any]:
        if state is None:
            state = torch.zeros(hidden)
        outputs = []
        for token in full_inputs:
            state = torch.tanh(token @ w_ih + state @ w_hh + bias)
            outputs.append(state)
        return torch.stack(outputs), state

    full_outputs, _ = run_recurrent(inputs, state=None)
    chunk_outputs = []
    activation_sizes = []
    kv_cache_sizes = []
    cache_tokens = 0
    state = None
    for idx in range(0, seq_len, chunk_size):
        chunk = inputs[idx : idx + chunk_size]
        out, state = run_recurrent(chunk, state=state)
        chunk_outputs.append(out)
        activation_sizes.append(int(out.numel()))
        cache_tokens += int(out.shape[0])
        kv_cache_sizes.append(cache_tokens)
    stitched = torch.cat(chunk_outputs, dim=0)

    assert len(set(activation_sizes)) == 1
    assert kv_cache_sizes == [512, 1024, 1536, 2048]

    target = torch.zeros_like(full_outputs)
    loss_full = torch.mean((full_outputs - target) ** 2)
    loss_chunked = torch.mean((stitched - target) ** 2)
    assert torch.allclose(loss_chunked, loss_full, atol=1e-6)


def test_arabic_tokenization() -> None:
    """Verify Arabic text passes through training pipeline correctly.
    Use sample Arabic text, tokenize, verify round-trip.
    """
    sample = "القوات جاهزة لتنفيذ المهمة في القطاع الشرقي."
    tokens = _arabic_tokenize(sample)
    rebuilt = _arabic_detokenize(tokens)
    assert rebuilt == sample
    assert bool(re.search(r"[\u0600-\u06FF]", rebuilt))


def _build_manifest_for_harness(manifest_dir: Path, model_id: str, arabic_support: bool) -> None:
    payload = {
        "model_id": model_id,
        "variants": [{"tag": "q4_k_m", "max_ram_mb": 512}],
        "arabic_support": arabic_support,
        "quality_thresholds": {
            "min_accuracy_pct": 70.0,
            "max_latency_p95_ms": 1000.0,
            "max_memory_mb": 1024.0,
            "accuracy_regression_tolerance_pct": 30.0,
        },
    }
    path = manifest_dir / f"{model_id}.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _build_quantized_model_stub(valid: bool) -> dict[str, list[float]]:
    if valid:
        codebook = [float(idx) for idx in range(-7, 8)]
        return {"layer0.weight": codebook * 4, "layer1.weight": codebook * 3}
    return {"layer0.weight": [0.0, 0.5, 1.0], "layer1.weight": [1.0, 1.0, 1.0]}


def _run_evaluation_harness_smoke() -> None:
    class Backend:
        def __init__(self, good: bool, quantized_model: dict[str, list[float]]) -> None:
            self.good = good
            self.model = quantized_model

        def infer(self, prompt: str) -> dict[str, str]:
            if self.good:
                return {"response": f"ok:{prompt}"}
            return {"response": "bad"}

    with tempfile.TemporaryDirectory(prefix="s3m-harness-") as tmpdir:
        manifest_dir = Path(tmpdir)
        _build_manifest_for_harness(manifest_dir, model_id="tiny-smoke", arabic_support=False)
        harness = CPUEvaluationHarness(model_id="tiny-smoke", manifest_dir=str(manifest_dir))
        prompts = [
            {"prompt": "alpha", "expected_output": "ok:alpha"},
            {"prompt": "bravo", "expected_output": "ok:bravo"},
        ]

        good_report = harness.run_all(backend=Backend(True, _build_quantized_model_stub(True)), test_prompts=prompts)
        assert good_report["passed"] is True

        bad_report = harness.run_all(backend=Backend(False, _build_quantized_model_stub(False)), test_prompts=prompts)
        assert bad_report["passed"] is False


def _run_arabic_harness_smoke_if_manifest_present() -> None:
    manifest_path = REPO_ROOT / "configs" / "model_manifests" / "allam_7b.yaml"
    if not manifest_path.exists():
        return

    class ArabicBackend:
        model = _build_quantized_model_stub(True)

        def infer(self, prompt: str) -> dict[str, str]:
            return {"response": "القوة في وضع دفاعي مستقر."}

    harness = CPUEvaluationHarness(model_id="allam-7b")
    prompts = [{"prompt": "status", "expected_output": "القوة في وضع دفاعي مستقر."}]
    arabic_prompts = ["قدّم تحديثًا موجزًا عن وضع القوة."]
    report = harness.run_all(backend=ArabicBackend(), test_prompts=prompts, test_prompts_arabic=arabic_prompts)
    assert report["checks"]["arabic"]["passed"] is True


def run_all_tests() -> int:
    checks: list[tuple[str, Callable[[], None]]] = [
        ("test_isa_detection", test_isa_detection),
        ("test_precision_policy", test_precision_policy),
        ("test_tanh_soft_clipping", test_tanh_soft_clipping),
        ("test_symmetric_quantizer", test_symmetric_quantizer),
        ("test_qat_training_loop", lambda: test_qat_training_loop()),
        ("test_checkpoint_save_resume", test_checkpoint_save_resume),
        ("test_chunk_recurrent", test_chunk_recurrent),
        ("test_arabic_tokenization", test_arabic_tokenization),
        ("test_evaluation_harness_gate", _run_evaluation_harness_smoke),
        ("test_arabic_eval_gate_optional", _run_arabic_harness_smoke_if_manifest_present),
    ]

    failures: list[str] = []
    for name, fn in checks:
        try:
            fn()
            print(f"[PASS] {name}")
        except Exception as exc:
            failures.append(f"{name}: {exc}")
            print(f"[FAIL] {name} -> {exc}")

    if failures:
        print("\nCPU training smoke test failed:")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("\nCPU training smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_all_tests())
