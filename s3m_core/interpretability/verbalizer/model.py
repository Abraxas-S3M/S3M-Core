"""Activation Verbalizer model for S3M interpretability.

Military/tactical context:
This module turns internal neural activations into plain-language intent
descriptions so operators can audit whether model cognition remains aligned
with mission-safe behavior during contested operations.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

try:
    import torch
    import torch.nn as nn
except ImportError as exc:  # pragma: no cover - import gate
    raise RuntimeError("ActivationVerbalizer requires torch to be installed.") from exc


DEFAULT_INSTRUCTION_PROMPT = (
    "Describe what the neural network is representing at this position. "
    "Be specific about intent, strategy, and emotional state."
)


class ActivationVerbalizer:
    """Translate token-level activations into short natural-language narratives."""

    def __init__(
        self,
        activation_dim: int,
        verbalizer_model_name: str = "microsoft/Phi-3-mini-4k-instruct",
    ) -> None:
        if activation_dim <= 0:
            raise ValueError("activation_dim must be positive.")
        if not verbalizer_model_name.strip():
            raise ValueError("verbalizer_model_name must be a non-empty string.")

        self.activation_dim = activation_dim
        self.verbalizer_model_name = verbalizer_model_name
        self._instruction_prompt = DEFAULT_INSTRUCTION_PROMPT
        self.model: Optional[Any] = None
        self.tokenizer: Optional[Any] = None
        self.model_embed_dim: Optional[int] = None
        self.projection: Optional[nn.Linear] = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def verbalize(self, activation: torch.Tensor) -> str:
        """Generate a short description for a single activation vector."""
        prepared_activation = self._prepare_activation(activation)
        prompt = self._instruction_prompt
        return self._generate_description(prepared_activation, prompt)

    def verbalize_sequence(self, activations: torch.Tensor) -> List[str]:
        """Generate one description for each token activation in a sequence."""
        if activations.ndim != 2:
            raise ValueError("activations must have shape [seq_len, activation_dim].")
        if activations.shape[1] != self.activation_dim:
            raise ValueError(
                f"Expected activation_dim={self.activation_dim}, got {activations.shape[1]}."
            )
        descriptions: List[str] = []
        for activation in activations:
            descriptions.append(self.verbalize(activation))
        return descriptions

    def verbalize_with_context(self, activation: torch.Tensor, surrounding_text: str) -> str:
        """Generate a description using activation and nearby text context."""
        if not isinstance(surrounding_text, str):
            raise TypeError("surrounding_text must be a string.")
        context = surrounding_text.strip()
        context_suffix = f"\n\nContext:\n{context}" if context else ""
        prompt = (
            f"{self._instruction_prompt}\n"
            "Use the provided text context to disambiguate latent intent."
            f"{context_suffix}"
        )
        prepared_activation = self._prepare_activation(activation)
        return self._generate_description(prepared_activation, prompt)

    def _ensure_model_ready(self) -> None:
        if self.model is None or self.tokenizer is None:
            self._load_verbalizer_components()
        if self.model_embed_dim is None:
            self.model_embed_dim = self._resolve_model_embed_dim()
        if self.projection is None:
            self.projection = nn.Linear(self.activation_dim, self.model_embed_dim).to(self.device)

    def _load_verbalizer_components(self) -> None:
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - optional dependency gate
            raise RuntimeError(
                "ActivationVerbalizer requires transformers. Install with pip install transformers."
            ) from exc

        # Tactical/offline posture: load only from local cache/image to avoid external dependencies.
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.verbalizer_model_name,
            local_files_only=True,
            trust_remote_code=True,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            self.verbalizer_model_name,
            local_files_only=True,
            trust_remote_code=True,
        ).to(self.device)
        self.model.eval()

    def _resolve_model_embed_dim(self) -> int:
        assert self.model is not None
        for attr in ("hidden_size", "n_embd", "d_model"):
            value = getattr(self.model.config, attr, None)
            if isinstance(value, int) and value > 0:
                return value
        raise RuntimeError("Unable to determine verbalizer embedding size from model config.")

    def _prepare_activation(self, activation: torch.Tensor) -> torch.Tensor:
        if not isinstance(activation, torch.Tensor):
            raise TypeError("activation must be a torch.Tensor.")
        if activation.ndim not in (1, 2):
            raise ValueError("activation must be 1D or [1, D].")
        if activation.ndim == 2:
            if activation.shape[0] != 1:
                raise ValueError("2D activation tensors must have shape [1, activation_dim].")
            activation = activation.squeeze(0)
        if activation.shape[0] != self.activation_dim:
            raise ValueError(
                f"Expected activation size {self.activation_dim}, got {activation.shape[0]}."
            )
        return activation.to(self.device, dtype=torch.float32)

    def _generate_description(self, activation: torch.Tensor, prompt: str) -> str:
        self._ensure_model_ready()
        assert self.tokenizer is not None
        assert self.model is not None
        assert self.projection is not None

        encoded = self.tokenizer(prompt, return_tensors="pt")
        input_ids = encoded["input_ids"].to(self.device)
        attention_mask = encoded["attention_mask"].to(self.device)

        token_embeddings = self.model.get_input_embeddings()(input_ids)
        soft_token = self.projection(activation.unsqueeze(0)).unsqueeze(1)
        inputs_embeds = torch.cat((soft_token, token_embeddings), dim=1)
        soft_attention = torch.ones((1, 1), dtype=attention_mask.dtype, device=self.device)
        full_attention = torch.cat((soft_attention, attention_mask), dim=1)

        generated = self.model.generate(
            inputs_embeds=inputs_embeds,
            attention_mask=full_attention,
            max_new_tokens=96,
            temperature=0.2,
            do_sample=False,
            pad_token_id=getattr(self.tokenizer, "eos_token_id", None),
        )
        text = self.tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        return self._truncate_to_three_sentences(text)

    @staticmethod
    def _truncate_to_three_sentences(text: str) -> str:
        if not text:
            return ""
        sentences = [
            fragment.strip()
            for fragment in re.split(r"(?<=[\.\!\?؟])\s+", text)
            if fragment.strip()
        ]
        if not sentences:
            return text.strip()
        return " ".join(sentences[:3]).strip()
