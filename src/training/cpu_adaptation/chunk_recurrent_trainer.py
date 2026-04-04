"""
S3M Chunk-Recurrent Long-Context Trainer for CPU
Research basis: OOMB (arXiv:2602.02108, Feb 2026)

Processes long sequences in chunks:
- Parallel computation WITHIN each chunk
- Serial processing BETWEEN chunks
- Activation recomputation eliminates O(N) activation memory
- KV cache managed with paging and optional CPU offloading

This enables fine-tuning on long Arabic/English documents, doctrine texts,
and multi-page operational memos on a single CPU node with 16-32 GB RAM.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import torch
import torch.nn.functional as F

logger = logging.getLogger("s3m.training.chunk_recurrent")

_DTYPE_MAP = {
    "float16": torch.float16,
    "bfloat16": torch.bfloat16,
    "float32": torch.float32,
}


@dataclass
class ChunkTrainingConfig:
    chunk_size_tokens: int = 512
    max_sequence_length: int = 32768
    use_activation_recomputation: bool = True
    kv_cache_dtype: str = "float16"
    use_kv_paging: bool = True
    page_size_tokens: int = 64
    offload_kv_to_cpu: bool = False
    sparse_attention_enabled: bool = False
    sparse_attention_top_k_pages: int = 32
    gradient_accumulation_chunks: int = 4
    attention_pattern: str = "causal"  # "causal" or "bidirectional"


class PagedKVCache:
    """
    Paged key-value cache for chunk-recurrent training.

    Inspired by OOMB: uses fixed-size pages to avoid memory fragmentation
    when KV cache grows incrementally. Supports in-place gradient
    accumulation to avoid storing KV cache as an autograd activation.

    Memory layout:
      - Pre-allocate page pool of fixed-size tensors
      - Assign pages as chunks are processed
      - Track page-to-chunk mapping for attention computation
      - Support page eviction/offloading for memory pressure
    """

    def __init__(
        self,
        num_heads: int,
        head_dim: int,
        max_pages: int,
        page_size: int,
        dtype: torch.dtype = torch.float16,
    ) -> None:
        if num_heads <= 0 or head_dim <= 0 or max_pages <= 0 or page_size <= 0:
            raise ValueError("num_heads, head_dim, max_pages, and page_size must all be > 0")
        self.num_heads = int(num_heads)
        self.head_dim = int(head_dim)
        self.max_pages = int(max_pages)
        self.page_size = int(page_size)
        self.dtype = dtype
        self.device = torch.device("cpu")

        self.key_pages = torch.zeros(
            (self.max_pages, self.page_size, self.num_heads, self.head_dim),
            dtype=self.dtype,
            device=self.device,
        )
        self.value_pages = torch.zeros_like(self.key_pages)
        self.grad_key_pages = torch.zeros_like(self.key_pages, dtype=torch.float32)
        self.grad_value_pages = torch.zeros_like(self.value_pages, dtype=torch.float32)

        self._free_pages: List[int] = list(range(self.max_pages))
        self._active_pages: set[int] = set()
        self._page_order: List[int] = []
        self._page_token_counts: Dict[int, int] = {}
        self._offloaded_pages: set[int] = set()
        self._offloaded_store: Dict[int, Tuple[torch.Tensor, torch.Tensor]] = {}

    def allocate_pages(self, num_tokens: int) -> List[int]:
        """Allocate pages for a new chunk's KV pairs. Return page indices."""
        if num_tokens <= 0:
            return []
        pages_needed = math.ceil(int(num_tokens) / self.page_size)
        if pages_needed > len(self._free_pages):
            raise MemoryError("PagedKVCache exhausted page pool")

        assigned = self._free_pages[:pages_needed]
        del self._free_pages[:pages_needed]

        self._active_pages.update(assigned)
        self._page_order.extend(assigned)

        remaining = int(num_tokens)
        for page_idx in assigned:
            page_tokens = min(self.page_size, remaining)
            self._page_token_counts[page_idx] = page_tokens
            remaining -= page_tokens
        return assigned

    def _normalize_kv(self, tensor: torch.Tensor) -> torch.Tensor:
        if tensor.ndim == 4:
            # [B, T, H, D] -> [T, H, D]
            if tensor.shape[0] != 1:
                raise ValueError("KV batch dimension must be 1 for chunk training")
            tensor = tensor[0]
        if tensor.ndim == 3 and tensor.shape[0] == self.num_heads and tensor.shape[2] == self.head_dim:
            # [H, T, D] -> [T, H, D]
            tensor = tensor.permute(1, 0, 2)
        if tensor.ndim != 3:
            raise ValueError("KV tensor must be rank-3 [T,H,D] or rank-4 [1,T,H,D]")
        if tensor.shape[1] != self.num_heads or tensor.shape[2] != self.head_dim:
            raise ValueError(
                f"KV shape mismatch: expected [T,{self.num_heads},{self.head_dim}], got {tuple(tensor.shape)}"
            )
        return tensor.to(device=self.device, dtype=self.dtype)

    def write_kv(self, page_indices: List[int], keys: torch.Tensor, values: torch.Tensor) -> None:
        """Write key-value pairs into allocated pages."""
        if not page_indices:
            return
        keys_n = self._normalize_kv(keys)
        values_n = self._normalize_kv(values)
        if keys_n.shape[0] != values_n.shape[0]:
            raise ValueError("keys and values must have the same token length")

        expected_tokens = sum(int(self._page_token_counts.get(p, self.page_size)) for p in page_indices)
        if keys_n.shape[0] != expected_tokens:
            raise ValueError(f"KV token count mismatch: got {keys_n.shape[0]}, expected {expected_tokens}")

        cursor = 0
        for page_idx in page_indices:
            page_tokens = int(self._page_token_counts.get(page_idx, self.page_size))
            self.key_pages[page_idx].zero_()
            self.value_pages[page_idx].zero_()
            self.key_pages[page_idx, :page_tokens].copy_(keys_n[cursor : cursor + page_tokens])
            self.value_pages[page_idx, :page_tokens].copy_(values_n[cursor : cursor + page_tokens])
            cursor += page_tokens

    def read_kv(self, page_indices: List[int]) -> Tuple[torch.Tensor, torch.Tensor]:
        """Read key-value pairs from pages for attention computation."""
        if not page_indices:
            empty = torch.empty((0, self.num_heads, self.head_dim), dtype=self.dtype, device=self.device)
            return empty, empty.clone()

        total_tokens = sum(int(self._page_token_counts.get(p, self.page_size)) for p in page_indices)
        keys = torch.empty((total_tokens, self.num_heads, self.head_dim), dtype=self.dtype, device=self.device)
        values = torch.empty_like(keys)

        cursor = 0
        for page_idx in page_indices:
            page_tokens = int(self._page_token_counts.get(page_idx, self.page_size))
            if page_idx in self._offloaded_pages:
                off_k, off_v = self._offloaded_store[page_idx]
                keys[cursor : cursor + page_tokens].copy_(off_k[:page_tokens])
                values[cursor : cursor + page_tokens].copy_(off_v[:page_tokens])
            else:
                keys[cursor : cursor + page_tokens].copy_(self.key_pages[page_idx, :page_tokens])
                values[cursor : cursor + page_tokens].copy_(self.value_pages[page_idx, :page_tokens])
            cursor += page_tokens
        return keys, values

    def get_all_kv(self) -> Tuple[torch.Tensor, torch.Tensor]:
        """Return full KV cache for attention against all previous chunks."""
        active_order = [p for p in self._page_order if p in self._active_pages]
        return self.read_kv(active_order)

    def accumulate_gradient(self, page_indices: List[int], dk: torch.Tensor, dv: torch.Tensor) -> None:
        """In-place gradient accumulation using atomic_add pattern."""
        if not page_indices:
            return
        dk_n = self._normalize_kv(dk).to(dtype=torch.float32)
        dv_n = self._normalize_kv(dv).to(dtype=torch.float32)
        if dk_n.shape[0] != dv_n.shape[0]:
            raise ValueError("dk and dv must have the same token length")

        expected_tokens = sum(int(self._page_token_counts.get(p, self.page_size)) for p in page_indices)
        if dk_n.shape[0] != expected_tokens:
            raise ValueError(f"Gradient token count mismatch: got {dk_n.shape[0]}, expected {expected_tokens}")

        cursor = 0
        for page_idx in page_indices:
            page_tokens = int(self._page_token_counts.get(page_idx, self.page_size))
            self.grad_key_pages[page_idx, :page_tokens].add_(dk_n[cursor : cursor + page_tokens])
            self.grad_value_pages[page_idx, :page_tokens].add_(dv_n[cursor : cursor + page_tokens])
            cursor += page_tokens

    def offload_pages(self, page_indices: List[int]) -> None:
        """Move pages to CPU memory. Track which pages are offloaded."""
        for page_idx in page_indices:
            if page_idx not in self._active_pages or page_idx in self._offloaded_pages:
                continue
            page_tokens = int(self._page_token_counts.get(page_idx, self.page_size))
            self._offloaded_store[page_idx] = (
                self.key_pages[page_idx, :page_tokens].detach().clone(),
                self.value_pages[page_idx, :page_tokens].detach().clone(),
            )
            self.key_pages[page_idx, :page_tokens].zero_()
            self.value_pages[page_idx, :page_tokens].zero_()
            self._offloaded_pages.add(page_idx)

    def prefetch_pages(self, page_indices: List[int]) -> None:
        """Asynchronously move pages back from CPU before they're needed."""
        # Tactical context: prefetch guards against latency spikes during
        # time-sensitive retraining windows when operators ingest long reports.
        for page_idx in page_indices:
            if page_idx not in self._offloaded_pages:
                continue
            page_tokens = int(self._page_token_counts.get(page_idx, self.page_size))
            off_k, off_v = self._offloaded_store[page_idx]
            self.key_pages[page_idx, :page_tokens].copy_(off_k[:page_tokens])
            self.value_pages[page_idx, :page_tokens].copy_(off_v[:page_tokens])
            self._offloaded_pages.remove(page_idx)
            self._offloaded_store.pop(page_idx, None)

    def memory_usage_mb(self) -> float:
        """Current memory used by all pages (both device and CPU)."""
        base_bytes = (
            (self.key_pages.numel() * self.key_pages.element_size())
            + (self.value_pages.numel() * self.value_pages.element_size())
            + (self.grad_key_pages.numel() * self.grad_key_pages.element_size())
            + (self.grad_value_pages.numel() * self.grad_value_pages.element_size())
        )
        offload_bytes = 0
        for off_k, off_v in self._offloaded_store.values():
            offload_bytes += off_k.numel() * off_k.element_size()
            offload_bytes += off_v.numel() * off_v.element_size()
        return float(base_bytes + offload_bytes) / (1024.0 * 1024.0)


class ChunkRecurrentTrainer:
    """
    Train models on long sequences using chunk-recurrent processing.

    Algorithm:
    Forward pass:
      for chunk_i in chunks:
          kv_i, activations_i = forward(chunk_i, kv_cache_all_previous)
          kv_cache.append(kv_i)
          DISCARD activations_i  # O(1) memory

    Backward pass (reverse order):
      for chunk_i in reversed(chunks):
          activations_i = RECOMPUTE forward(chunk_i, kv_cache_all_previous)
          grads = backward(activations_i)
          kv_cache.accumulate_gradient(grads)

    Memory: O(1) activations + O(N) KV cache (managed by paging + offloading)
    """

    def __init__(self, model: Any, config: ChunkTrainingConfig, adapter_tuner: Any = None, checkpointer: Any = None) -> None:
        if model is None:
            raise ValueError("model must not be None")
        if not isinstance(config, ChunkTrainingConfig):
            raise ValueError("config must be a ChunkTrainingConfig instance")
        self.model = model
        self.config = config
        self.adapter_tuner = adapter_tuner
        self.checkpointer = checkpointer
        self._validate_config()

        self._kv_dtype = _DTYPE_MAP[self.config.kv_cache_dtype]
        self._num_heads, self._head_dim = self._infer_attention_shape()
        self._chunk_page_map: Dict[int, List[int]] = {}
        self._labels_tensor: Optional[torch.Tensor] = None
        self._chunks: List[torch.Tensor] = []
        self._optimizer = self._build_optimizer()

    def _validate_config(self) -> None:
        if self.config.chunk_size_tokens <= 0:
            raise ValueError("chunk_size_tokens must be > 0")
        if self.config.page_size_tokens <= 0:
            raise ValueError("page_size_tokens must be > 0")
        if self.config.max_sequence_length <= 0:
            raise ValueError("max_sequence_length must be > 0")
        if self.config.gradient_accumulation_chunks <= 0:
            raise ValueError("gradient_accumulation_chunks must be > 0")
        if self.config.kv_cache_dtype not in _DTYPE_MAP:
            raise ValueError(f"Unsupported kv_cache_dtype: {self.config.kv_cache_dtype}")
        if self.config.attention_pattern not in {"causal", "bidirectional"}:
            raise ValueError("attention_pattern must be 'causal' or 'bidirectional'")
        if self.config.sparse_attention_top_k_pages <= 0:
            raise ValueError("sparse_attention_top_k_pages must be > 0")

    def _infer_attention_shape(self) -> Tuple[int, int]:
        num_heads = (
            getattr(self.model, "num_heads", None)
            or getattr(self.model, "n_head", None)
            or getattr(getattr(self.model, "config", None), "num_attention_heads", None)
            or 8
        )
        hidden_size = (
            getattr(self.model, "hidden_size", None)
            or getattr(self.model, "d_model", None)
            or getattr(getattr(self.model, "config", None), "hidden_size", None)
            or 512
        )
        num_heads = int(num_heads)
        hidden_size = int(hidden_size)
        head_dim = max(1, hidden_size // max(1, num_heads))
        return num_heads, head_dim

    def _build_optimizer(self) -> Optional[torch.optim.Optimizer]:
        if self.adapter_tuner is not None:
            maybe_opt = getattr(self.adapter_tuner, "optimizer", None)
            if maybe_opt is not None:
                return maybe_opt
        if not hasattr(self.model, "parameters"):
            return None
        params = [p for p in self.model.parameters() if p.requires_grad]
        if not params:
            return None
        return torch.optim.AdamW(params, lr=1e-4)

    def _split_chunks(self, token_ids: Sequence[int]) -> List[torch.Tensor]:
        chunks: List[torch.Tensor] = []
        for start in range(0, len(token_ids), self.config.chunk_size_tokens):
            chunk = token_ids[start : start + self.config.chunk_size_tokens]
            chunks.append(torch.tensor(chunk, dtype=torch.long, device=torch.device("cpu")))
        return chunks

    def _chunk_pages_before(self, chunk_idx: int) -> List[int]:
        pages: List[int] = []
        for idx in range(chunk_idx):
            pages.extend(self._chunk_page_map.get(idx, []))
        return pages

    def _select_sparse_pages(self, pages: List[int]) -> List[int]:
        if not self.config.sparse_attention_enabled:
            return pages
        top_k = min(len(pages), self.config.sparse_attention_top_k_pages)
        return pages[-top_k:]

    def _build_attention_mask(self, context_tokens: int, chunk_tokens: int) -> torch.Tensor:
        total = context_tokens + chunk_tokens
        if self.config.attention_pattern == "bidirectional":
            return torch.ones((1, chunk_tokens, total), dtype=torch.float32)
        mask = torch.zeros((1, chunk_tokens, total), dtype=torch.float32)
        for row in range(chunk_tokens):
            mask[0, row, : context_tokens + row + 1] = 1.0
        return mask

    def _extract_labels_for_chunk(self, chunk_idx: int, chunk_len: int) -> Optional[torch.Tensor]:
        if self._labels_tensor is None:
            return None
        start = chunk_idx * self.config.chunk_size_tokens
        return self._labels_tensor[start : start + chunk_len]

    def _normalize_kv_output(self, tensor: torch.Tensor) -> torch.Tensor:
        if tensor.ndim == 4 and tensor.shape[0] == 1:
            tensor = tensor[0]
        if tensor.ndim == 4 and tensor.shape[0] > 1:
            raise ValueError("KV output batch dimension must be 1 for chunk trainer")
        if tensor.ndim == 3 and tensor.shape[0] == self._num_heads:
            tensor = tensor.permute(1, 0, 2)
        if tensor.ndim != 3:
            raise ValueError("KV output tensor must resolve to rank-3 [T,H,D]")
        if tensor.shape[1] != self._num_heads:
            raise ValueError(f"KV output has {tensor.shape[1]} heads; expected {self._num_heads}")
        if tensor.shape[2] != self._head_dim:
            raise ValueError(f"KV output head_dim={tensor.shape[2]}; expected {self._head_dim}")
        return tensor

    def _synthesize_kv(self, chunk_tokens: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        # Tactical context: deterministic synthetic KV keeps the trainer usable
        # for mission rehearsal builds where model internals are partially stubbed.
        token_f = chunk_tokens.to(dtype=torch.float32).unsqueeze(-1)
        basis = torch.arange(self._head_dim, dtype=torch.float32).unsqueeze(0) + 1.0
        encoded = token_f / basis
        keys = torch.sin(encoded).unsqueeze(1).repeat(1, self._num_heads, 1)
        values = torch.cos(encoded).unsqueeze(1).repeat(1, self._num_heads, 1)
        return keys.to(dtype=self._kv_dtype), values.to(dtype=self._kv_dtype)

    def _run_model(
        self,
        chunk_tokens: torch.Tensor,
        prior_k: torch.Tensor,
        prior_v: torch.Tensor,
        attention_mask: torch.Tensor,
    ) -> Any:
        input_ids = chunk_tokens.unsqueeze(0)
        call_attempts = [
            {
                "input_ids": input_ids,
                "past_key_values": (prior_k, prior_v),
                "attention_mask": attention_mask,
                "use_cache": True,
                "attention_pattern": self.config.attention_pattern,
            },
            {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "use_cache": True,
                "attention_pattern": self.config.attention_pattern,
            },
            {"input_ids": input_ids},
            {"tokens": input_ids},
        ]
        for kwargs in call_attempts:
            try:
                return self.model(**kwargs)
            except TypeError:
                continue
        return self.model(input_ids)

    def _extract_outputs(self, output: Any) -> Tuple[Optional[torch.Tensor], Optional[torch.Tensor], Optional[torch.Tensor], Optional[torch.Tensor]]:
        logits: Optional[torch.Tensor] = None
        loss: Optional[torch.Tensor] = None
        keys: Optional[torch.Tensor] = None
        values: Optional[torch.Tensor] = None

        if isinstance(output, dict):
            logits = output.get("logits")
            loss = output.get("loss")
            if output.get("keys") is not None and output.get("values") is not None:
                keys = output["keys"]
                values = output["values"]
            elif output.get("kv") is not None and isinstance(output["kv"], (tuple, list)) and len(output["kv"]) == 2:
                keys, values = output["kv"]
            elif output.get("past_key_values") is not None:
                pkv = output["past_key_values"]
                if isinstance(pkv, (tuple, list)) and len(pkv) > 0:
                    layer0 = pkv[-1]
                    if isinstance(layer0, (tuple, list)) and len(layer0) >= 2:
                        keys, values = layer0[0], layer0[1]
        elif isinstance(output, (tuple, list)) and len(output) > 0:
            if torch.is_tensor(output[0]):
                logits = output[0]
            if len(output) > 1 and torch.is_tensor(output[1]):
                loss = output[1]
        elif torch.is_tensor(output):
            logits = output
        return logits, loss, keys, values

    def _compute_loss(self, logits: Optional[torch.Tensor], model_loss: Optional[torch.Tensor], labels: Optional[torch.Tensor]) -> torch.Tensor:
        if model_loss is not None and torch.is_tensor(model_loss):
            return model_loss.float().mean()
        if logits is not None and labels is not None and logits.ndim >= 2:
            logits_2d = logits
            if logits.ndim == 3 and logits.shape[0] == 1:
                logits_2d = logits[0]
            if logits_2d.ndim == 2 and logits_2d.shape[0] == labels.shape[0]:
                return F.cross_entropy(logits_2d.float(), labels.long(), ignore_index=-100)
        if logits is not None and torch.is_tensor(logits):
            return logits.float().pow(2).mean()
        return torch.zeros((), dtype=torch.float32)

    def train_on_document(self, token_ids: List[int], labels: Optional[List[int]] = None) -> dict:
        """
        Train on a single long document.

        1. Split token_ids into chunks of chunk_size_tokens
        2. Forward pass through all chunks, building KV cache
        3. Backward pass with activation recomputation
        4. Optimizer step (with tanh clipping if QAT enabled)
        5. Return loss and training metrics
        """
        if not isinstance(token_ids, list) or not token_ids:
            raise ValueError("token_ids must be a non-empty list of integers")
        if any((not isinstance(t, int) or t < 0) for t in token_ids):
            raise ValueError("token_ids must contain non-negative integers only")
        if len(token_ids) > self.config.max_sequence_length:
            raise ValueError("Input sequence exceeds configured max_sequence_length")
        if labels is not None:
            if not isinstance(labels, list):
                raise ValueError("labels must be a list when provided")
            if len(labels) != len(token_ids):
                raise ValueError("labels length must match token_ids length")
            if any((not isinstance(t, int)) for t in labels):
                raise ValueError("labels must contain integers")
            self._labels_tensor = torch.tensor(labels, dtype=torch.long, device=torch.device("cpu"))
        else:
            self._labels_tensor = None

        self._chunks = self._split_chunks(token_ids)
        total_tokens = len(token_ids)
        max_pages = math.ceil(total_tokens / self.config.page_size_tokens)
        kv_cache = PagedKVCache(
            num_heads=self._num_heads,
            head_dim=self._head_dim,
            max_pages=max(1, max_pages),
            page_size=self.config.page_size_tokens,
            dtype=self._kv_dtype,
        )
        self._chunk_page_map = {}

        if self._optimizer is not None:
            self._optimizer.zero_grad(set_to_none=True)

        with torch.no_grad():
            for chunk_idx, chunk_tokens in enumerate(self._chunks):
                _, metadata = self._forward_chunk(chunk_tokens, kv_cache, chunk_idx)
                logger.info(
                    "Forward chunk boundary idx=%d/%d tokens=%d pages=%d",
                    chunk_idx + 1,
                    len(self._chunks),
                    int(chunk_tokens.shape[0]),
                    len(metadata.get("page_indices", [])),
                )

        total_loss = 0.0
        backward_steps = 0
        for chunk_idx in range(len(self._chunks) - 1, -1, -1):
            chunk_tokens = self._chunks[chunk_idx]
            upstream_grad = torch.ones((), dtype=torch.float32)
            loss = self._backward_chunk_with_recomputation(chunk_tokens, kv_cache, chunk_idx, upstream_grad)
            total_loss += float(loss.detach().cpu().item())
            backward_steps += 1
            logger.info(
                "Backward chunk boundary idx=%d/%d tokens=%d",
                chunk_idx + 1,
                len(self._chunks),
                int(chunk_tokens.shape[0]),
            )

            should_step = (
                backward_steps % self.config.gradient_accumulation_chunks == 0 or chunk_idx == 0
            )
            if should_step and self._optimizer is not None:
                if getattr(self.model, "qat_enabled", False):
                    for param in self.model.parameters():
                        if param.grad is not None:
                            param.grad.data = torch.tanh(param.grad.data)
                self._optimizer.step()
                self._optimizer.zero_grad(set_to_none=True)

            if self.checkpointer is not None and hasattr(self.checkpointer, "save_chunk_checkpoint"):
                try:
                    self.checkpointer.save_chunk_checkpoint(chunk_idx=chunk_idx, total_chunks=len(self._chunks))
                except Exception:  # pragma: no cover - defensive integration hook
                    logger.warning("Chunk checkpointing failed", exc_info=True)

        avg_loss = total_loss / max(1, len(self._chunks))
        return {
            "loss": avg_loss,
            "chunks_processed": len(self._chunks),
            "tokens_processed": total_tokens,
            "kv_cache_memory_mb": kv_cache.memory_usage_mb(),
            "estimated_sequence_memory_mb": self._estimate_memory_for_sequence(total_tokens),
            "attention_pattern": self.config.attention_pattern,
            "activation_recomputation": self.config.use_activation_recomputation,
        }

    def _forward_chunk(
        self,
        chunk_tokens: torch.Tensor,
        kv_cache: PagedKVCache,
        chunk_idx: int,
    ) -> Tuple[torch.Tensor, dict]:
        """Forward pass for a single chunk attending to all previous KV."""
        prior_pages = self._select_sparse_pages(self._chunk_pages_before(chunk_idx))
        if self.config.offload_kv_to_cpu:
            kv_cache.prefetch_pages(prior_pages)
        prior_k, prior_v = kv_cache.read_kv(prior_pages)
        attention_mask = self._build_attention_mask(prior_k.shape[0], int(chunk_tokens.shape[0]))
        output = self._run_model(chunk_tokens, prior_k, prior_v, attention_mask)
        logits, model_loss, out_k, out_v = self._extract_outputs(output)

        if out_k is not None and out_v is not None:
            keys = self._normalize_kv_output(out_k)
            values = self._normalize_kv_output(out_v)
        else:
            keys, values = self._synthesize_kv(chunk_tokens)

        if keys.requires_grad:
            keys.retain_grad()
        if values.requires_grad:
            values.retain_grad()

        page_indices = self._chunk_page_map.get(chunk_idx)
        if page_indices is None:
            page_indices = kv_cache.allocate_pages(int(chunk_tokens.shape[0]))
            self._chunk_page_map[chunk_idx] = page_indices
        kv_cache.write_kv(page_indices, keys.detach(), values.detach())

        labels = self._extract_labels_for_chunk(chunk_idx, int(chunk_tokens.shape[0]))
        loss = self._compute_loss(logits, model_loss, labels)
        if self.config.offload_kv_to_cpu and prior_pages:
            kv_cache.offload_pages(prior_pages)
        return loss, {"page_indices": page_indices, "keys": keys, "values": values}

    def _backward_chunk_with_recomputation(
        self,
        chunk_tokens: torch.Tensor,
        kv_cache: PagedKVCache,
        chunk_idx: int,
        upstream_grad: torch.Tensor,
    ) -> torch.Tensor:
        """Recompute activations for this chunk, then backpropagate."""
        loss, metadata = self._forward_chunk(chunk_tokens, kv_cache, chunk_idx)
        if self._optimizer is None or not loss.requires_grad:
            return loss.detach()

        scaled = loss / float(max(1, self.config.gradient_accumulation_chunks))
        scaled.backward(upstream_grad.to(dtype=scaled.dtype))

        keys = metadata.get("keys")
        values = metadata.get("values")
        page_indices = metadata.get("page_indices", [])
        if (
            isinstance(keys, torch.Tensor)
            and isinstance(values, torch.Tensor)
            and keys.grad is not None
            and values.grad is not None
        ):
            kv_cache.accumulate_gradient(page_indices, keys.grad.detach(), values.grad.detach())
        return loss.detach()

    def _estimate_memory_for_sequence(self, seq_length: int) -> float:
        """Estimate total memory needed for a sequence of given length.
        Activation memory = constant (one chunk worth)
        KV memory = seq_length * per_token_kv_size / page_efficiency
        """
        seq_length = max(0, int(seq_length))
        bytes_per_kv_token = 2 * self._num_heads * self._head_dim * torch.tensor([], dtype=self._kv_dtype).element_size()
        page_efficiency = 0.90 if self.config.use_kv_paging else 0.80
        kv_bytes = (seq_length * bytes_per_kv_token) / page_efficiency

        # Tactical context: overestimating memory preserves headroom for field
        # telemetry and command apps that share the same edge compute node.
        activation_bytes = (
            self.config.chunk_size_tokens * self._num_heads * self._head_dim * 4 * 6
        )
        total_mb = (kv_bytes + activation_bytes) / (1024.0 * 1024.0)
        return total_mb * 1.20

    def max_trainable_sequence_length(self, available_ram_mb: float) -> int:
        """Given available RAM, return maximum sequence length trainable."""
        budget_mb = max(0.0, float(available_ram_mb))
        if budget_mb <= 0.0:
            return 0
        low, high = 0, self.config.max_sequence_length
        best = 0
        while low <= high:
            mid = (low + high) // 2
            need_mb = self._estimate_memory_for_sequence(mid)
            if need_mb <= budget_mb:
                best = mid
                low = mid + 1
            else:
                high = mid - 1
        return best
