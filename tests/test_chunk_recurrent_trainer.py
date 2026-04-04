"""Unit tests for chunk-recurrent CPU long-context trainer."""

from __future__ import annotations

import pytest
torch = pytest.importorskip("torch")

from src.training.cpu_adaptation.chunk_recurrent_trainer import (
    ChunkRecurrentTrainer,
    ChunkTrainingConfig,
    PagedKVCache,
)


class DummyChunkModel(torch.nn.Module):
    """Minimal token model that exposes logits and KV tensors."""

    def __init__(self, vocab_size: int = 256, hidden_size: int = 16, num_heads: int = 2) -> None:
        super().__init__()
        self.embedding = torch.nn.Embedding(vocab_size, hidden_size)
        self.out_proj = torch.nn.Linear(hidden_size, vocab_size)
        self.k_proj = torch.nn.Linear(hidden_size, hidden_size)
        self.v_proj = torch.nn.Linear(hidden_size, hidden_size)
        self.num_heads = num_heads
        self.hidden_size = hidden_size
        self.head_dim = hidden_size // num_heads

    def forward(self, input_ids: torch.Tensor, **_: object) -> dict:
        hidden = self.embedding(input_ids)
        logits = self.out_proj(hidden)
        batch_size, seq_len, _ = hidden.shape
        keys = self.k_proj(hidden).reshape(batch_size, seq_len, self.num_heads, self.head_dim)
        values = self.v_proj(hidden).reshape(batch_size, seq_len, self.num_heads, self.head_dim)
        return {"logits": logits, "keys": keys, "values": values}


def test_paged_kv_cache_roundtrip_gradient_and_offload() -> None:
    cache = PagedKVCache(num_heads=2, head_dim=4, max_pages=8, page_size=3, dtype=torch.float16)
    pages = cache.allocate_pages(7)
    assert len(pages) == 3

    keys = torch.arange(7 * 2 * 4, dtype=torch.float16).reshape(7, 2, 4)
    values = keys + 1
    cache.write_kv(pages, keys, values)

    read_k, read_v = cache.read_kv(pages)
    assert torch.equal(read_k, keys)
    assert torch.equal(read_v, values)

    dk = torch.ones_like(keys, dtype=torch.float32)
    dv = torch.ones_like(values, dtype=torch.float32) * 2.0
    cache.accumulate_gradient(pages, dk, dv)
    grad_sum = cache.grad_key_pages[pages[0], :3].sum().item()
    assert grad_sum == pytest.approx(float(3 * 2 * 4), rel=0.0, abs=1e-5)

    cache.offload_pages([pages[0]])
    off_k, _ = cache.read_kv([pages[0]])
    assert torch.equal(off_k, keys[:3])
    cache.prefetch_pages([pages[0]])
    pre_k, _ = cache.read_kv([pages[0]])
    assert torch.equal(pre_k, keys[:3])
    assert cache.memory_usage_mb() > 0.0


@pytest.mark.parametrize("attention_pattern", ["causal", "bidirectional"])
def test_chunk_recurrent_trainer_document_training(attention_pattern: str) -> None:
    model = DummyChunkModel()
    config = ChunkTrainingConfig(
        chunk_size_tokens=8,
        page_size_tokens=4,
        max_sequence_length=64,
        gradient_accumulation_chunks=2,
        attention_pattern=attention_pattern,
    )
    trainer = ChunkRecurrentTrainer(model=model, config=config)
    token_ids = [i % 128 for i in range(24)]
    labels = [(i + 1) % 128 for i in range(24)]

    before = model.out_proj.weight.detach().clone()
    metrics = trainer.train_on_document(token_ids=token_ids, labels=labels)
    after = model.out_proj.weight.detach()

    assert metrics["chunks_processed"] == 3
    assert metrics["tokens_processed"] == 24
    assert metrics["attention_pattern"] == attention_pattern
    assert metrics["kv_cache_memory_mb"] > 0.0
    assert not torch.allclose(before, after)


def test_memory_estimate_has_safety_margin_and_sequence_bound() -> None:
    model = DummyChunkModel(hidden_size=32, num_heads=4)
    config = ChunkTrainingConfig(
        chunk_size_tokens=16,
        page_size_tokens=8,
        max_sequence_length=4096,
        kv_cache_dtype="float16",
    )
    trainer = ChunkRecurrentTrainer(model=model, config=config)

    seq_len = 256
    estimate = trainer._estimate_memory_for_sequence(seq_len)
    bytes_per_kv_token = 2 * trainer._num_heads * trainer._head_dim * torch.tensor([], dtype=trainer._kv_dtype).element_size()
    raw_kv_mb = ((seq_len * bytes_per_kv_token) / 0.90) / (1024.0 * 1024.0)
    raw_activation_mb = (config.chunk_size_tokens * trainer._num_heads * trainer._head_dim * 4 * 6) / (1024.0 * 1024.0)
    raw_total_mb = raw_kv_mb + raw_activation_mb
    assert estimate >= raw_total_mb * 1.20 - 1e-9

    budget = trainer._estimate_memory_for_sequence(512)
    assert trainer.max_trainable_sequence_length(budget) >= 512
    assert trainer.max_trainable_sequence_length(budget * 0.5) < 512
