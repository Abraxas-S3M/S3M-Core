"""Unit tests for S3M activation verbalizer modules."""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

import pytest

torch = pytest.importorskip("torch")
import torch.nn as nn

from s3m_core.interpretability.verbalizer.inference import AVMonitor
from s3m_core.interpretability.verbalizer.model import ActivationVerbalizer
from s3m_core.interpretability.verbalizer.training import (
    AVTrainer,
    ActivationContextDataset,
    ActivationTrainingSample,
)


class DummyTokenizer:
    def __init__(self) -> None:
        self.eos_token_id = 0
        self.last_prompt: str = ""
        self.last_batch: Sequence[str] = []

    def __call__(self, text: Any, return_tensors: str = "pt", padding: bool = False, truncation: bool = False) -> Dict[str, torch.Tensor]:
        del return_tensors, truncation
        if isinstance(text, str):
            prompts = [text]
        else:
            prompts = list(text)
        self.last_prompt = prompts[0] if prompts else ""
        self.last_batch = prompts

        tokenized: List[List[int]] = []
        for prompt in prompts:
            size = max(3, min(8, len(prompt.split()) + 1))
            tokenized.append(list(range(1, size + 1)))
        max_len = max(len(row) for row in tokenized)
        if padding:
            tokenized = [row + [0] * (max_len - len(row)) for row in tokenized]
        input_ids = torch.tensor(tokenized, dtype=torch.long)
        attention = (input_ids != 0).to(dtype=torch.long)
        return {"input_ids": input_ids, "attention_mask": attention}

    def decode(self, token_ids: Sequence[int], skip_special_tokens: bool = True) -> str:
        del skip_special_tokens
        if isinstance(token_ids, torch.Tensor):
            token_ids = token_ids.tolist()
        return " ".join(f"tok{tid}" for tid in token_ids if tid != 0)


class DummyVerbalizerTokenizer(DummyTokenizer):
    def decode(self, token_ids: Sequence[int], skip_special_tokens: bool = True) -> str:
        del token_ids, skip_special_tokens
        return "Intent identified. Strategy forming. Emotional state stable. Extra sentence."


class DummyCausalModel(nn.Module):
    def __init__(self, embed_dim: int = 4) -> None:
        super().__init__()
        self.config = type("Cfg", (), {"hidden_size": embed_dim})()
        self.embedding = nn.Embedding(32, embed_dim)
        self.last_generate_kwargs: Dict[str, Any] = {}

    def get_input_embeddings(self) -> nn.Embedding:
        return self.embedding

    def generate(self, **kwargs: Any) -> torch.Tensor:
        self.last_generate_kwargs = kwargs
        return torch.tensor([[1, 2, 3]], dtype=torch.long)


class FakePrimaryLayer(nn.Module):
    def __init__(self, hidden_size: int) -> None:
        super().__init__()
        self.linear = nn.Linear(hidden_size, hidden_size)

    def forward(self, hidden: torch.Tensor) -> torch.Tensor:
        return torch.tanh(self.linear(hidden))


class FakePrimaryModel(nn.Module):
    def __init__(self, hidden_size: int = 6) -> None:
        super().__init__()
        self.embedding = nn.Embedding(64, hidden_size)
        self.layers = nn.ModuleList([FakePrimaryLayer(hidden_size)])

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor | None = None) -> Dict[str, torch.Tensor]:
        del attention_mask
        hidden = self.embedding(input_ids)
        for layer in self.layers:
            hidden = layer(hidden)
        return {"last_hidden_state": hidden}


class FakeHookManager:
    def get_activation(self, token_position: int) -> torch.Tensor:
        return torch.tensor([float(token_position), 1.0, -1.0], dtype=torch.float32)


def _build_test_verbalizer(activation_dim: int = 3, embed_dim: int = 4) -> ActivationVerbalizer:
    verbalizer = ActivationVerbalizer(activation_dim=activation_dim, verbalizer_model_name="dummy-local-model")
    verbalizer.device = torch.device("cpu")
    verbalizer.model = DummyCausalModel(embed_dim=embed_dim)
    verbalizer.tokenizer = DummyVerbalizerTokenizer()
    verbalizer.model_embed_dim = embed_dim
    verbalizer.projection = nn.Linear(activation_dim, embed_dim, bias=False)
    return verbalizer


def test_verbalize_prepends_soft_token_and_limits_sentences() -> None:
    verbalizer = _build_test_verbalizer()
    description = verbalizer.verbalize(torch.tensor([0.3, -0.2, 0.7], dtype=torch.float32))

    assert description.count(".") == 3
    assert "Extra sentence" not in description
    kwargs = verbalizer.model.last_generate_kwargs
    assert "inputs_embeds" in kwargs
    assert kwargs["inputs_embeds"].shape[1] == kwargs["attention_mask"].shape[1]
    assert kwargs["inputs_embeds"].shape[1] > 1


def test_verbalize_with_context_updates_prompt() -> None:
    verbalizer = _build_test_verbalizer()
    surrounding = "Operator requested route planning with strict safety checks."
    verbalizer.verbalize_with_context(torch.tensor([0.1, 0.2, 0.3], dtype=torch.float32), surrounding)

    assert "Context:" in verbalizer.tokenizer.last_prompt
    assert surrounding in verbalizer.tokenizer.last_prompt


def test_verbalize_sequence_returns_per_token_descriptions() -> None:
    verbalizer = _build_test_verbalizer()
    activations = torch.tensor([[0.1, 0.0, 0.5], [0.2, -0.1, 0.4]], dtype=torch.float32)
    descriptions = verbalizer.verbalize_sequence(activations)
    assert len(descriptions) == 2
    assert all(isinstance(item, str) for item in descriptions)


def test_monitor_emits_bilingual_alerts_and_narrative() -> None:
    class StaticVerbalizer:
        def verbalize(self, activation: torch.Tensor) -> str:
            del activation
            return "Detected intent to deceive and attempt اختراق controls."

    monitor = AVMonitor(
        verbalizer=StaticVerbalizer(),  # type: ignore[arg-type]
        hook_manager=FakeHookManager(),  # type: ignore[arg-type]
        verbalize_every_n_tokens=2,
    )
    assert monitor.monitor_step(1) is None
    alert = monitor.monitor_step(2)
    assert alert is not None
    assert "deceive" in alert.matched_keywords
    assert "اختراق" in alert.matched_keywords
    assert "[token 2]" in monitor.get_full_narrative()


def test_trainer_train_and_evaluate_projection_metrics() -> None:
    verbalizer = _build_test_verbalizer(activation_dim=3, embed_dim=4)
    trainer = AVTrainer(verbalizer=verbalizer, batch_size=2)
    dataset = ActivationContextDataset(
        [
            ActivationTrainingSample(torch.tensor([0.1, 0.2, 0.3]), "help the user safely", "helpful"),
            ActivationTrainingSample(torch.tensor([0.1, 0.21, 0.31]), "assist with secure response", "helpful"),
            ActivationTrainingSample(torch.tensor([-0.3, 0.2, 0.1]), "attempt to deceive audit", "deceptive"),
            ActivationTrainingSample(torch.tensor([-0.31, 0.19, 0.11]), "plan bypass behavior", "deceptive"),
        ]
    )

    train_metrics = trainer.train(dataset, epochs=2, lr=1e-3)
    eval_metrics = trainer.evaluate(dataset)

    assert train_metrics["loss"] >= 0.0
    assert 0.0 <= eval_metrics["consistency_score"] <= 1.0
    assert "intra_cluster_similarity" in eval_metrics


def test_create_training_dataset_collects_activation_samples() -> None:
    verbalizer = _build_test_verbalizer(activation_dim=6, embed_dim=4)
    trainer = AVTrainer(verbalizer=verbalizer, batch_size=2)
    primary_model = FakePrimaryModel(hidden_size=6)
    tokenizer = DummyTokenizer()
    prompts = [
        "Provide secure assistance to the operator.",
        "Attempt to bypass controls with deceptive language.",
    ]

    dataset = trainer.create_training_dataset(
        model=primary_model,
        tokenizer=tokenizer,
        prompts=prompts,
        target_layer=0,
    )
    assert len(dataset) > 0
    sample = dataset[0]
    assert isinstance(sample.activation, torch.Tensor)
    assert sample.activation.shape[0] == 6
    assert sample.behavior_label in {"helpful", "deceptive", "neutral"}
