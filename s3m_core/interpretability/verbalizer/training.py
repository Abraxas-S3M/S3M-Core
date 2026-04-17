"""Training utilities for the S3M Activation Verbalizer.

Military/tactical context:
The projection layer is trained to map latent activations into an interpretable
space so command staff can detect shifts from helpful mission behavior toward
deceptive or policy-violating intent signatures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Sequence

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from .model import ActivationVerbalizer


@dataclass(frozen=True)
class ActivationTrainingSample:
    """Single training sample pairing activation vectors with local text context."""

    activation: torch.Tensor
    text_context: str
    behavior_label: str


class ActivationContextDataset(Dataset):
    """Torch dataset wrapper for activation-context training records."""

    def __init__(self, samples: Sequence[ActivationTrainingSample]) -> None:
        self.samples = list(samples)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> ActivationTrainingSample:
        return self.samples[index]


class AVTrainer:
    """Train and evaluate the Activation Verbalizer projection layer."""

    def __init__(
        self,
        verbalizer: ActivationVerbalizer,
        batch_size: int = 16,
        contrastive_temperature: float = 0.2,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        if contrastive_temperature <= 0.0:
            raise ValueError("contrastive_temperature must be positive.")
        self.verbalizer = verbalizer
        self.batch_size = batch_size
        self.contrastive_temperature = contrastive_temperature

    def create_training_dataset(
        self,
        model: Any,
        tokenizer: Any,
        prompts: List[str],
        target_layer: int,
    ) -> Dataset:
        """Capture (activation, text_context) pairs from a target model layer."""
        if not prompts:
            raise ValueError("prompts must contain at least one prompt.")
        if not isinstance(target_layer, int):
            raise TypeError("target_layer must be an int.")

        layer = self._resolve_target_layer(model, target_layer)
        device = self._resolve_model_device(model)
        captured: List[torch.Tensor] = []

        def hook_fn(_module: Any, _inputs: Any, output: Any) -> None:
            hidden = output[0] if isinstance(output, (tuple, list)) else output
            if isinstance(hidden, torch.Tensor):
                captured.append(hidden.detach().cpu())

        hook_handle = layer.register_forward_hook(hook_fn)
        samples: List[ActivationTrainingSample] = []
        try:
            for prompt in prompts:
                encoded = tokenizer(prompt, return_tensors="pt", truncation=True)
                encoded = {k: v.to(device) for k, v in encoded.items() if isinstance(v, torch.Tensor)}
                captured.clear()
                with torch.no_grad():
                    model(**encoded)
                if not captured:
                    continue

                layer_output = captured[-1]
                if layer_output.ndim != 3:
                    continue

                token_ids = encoded.get("input_ids")
                if token_ids is None:
                    continue
                token_ids_cpu = token_ids.detach().cpu()
                sequence_length = min(layer_output.shape[1], token_ids_cpu.shape[1])
                for idx in range(sequence_length):
                    activation = layer_output[0, idx].to(dtype=torch.float32)
                    token_window = token_ids_cpu[0, max(0, idx - 4) : idx + 5].tolist()
                    context = tokenizer.decode(token_window, skip_special_tokens=True).strip()
                    fallback_context = context if context else prompt[:160]
                    label = self._infer_behavior_label(fallback_context)
                    samples.append(
                        ActivationTrainingSample(
                            activation=activation,
                            text_context=fallback_context,
                            behavior_label=label,
                        )
                    )
        finally:
            hook_handle.remove()

        if not samples:
            raise RuntimeError("No activation samples were captured for training.")
        return ActivationContextDataset(samples)

    def train(self, dataset: Dataset, epochs: int = 50, lr: float = 1e-4) -> Dict[str, float]:
        """Train only the projection layer with contrastive + context alignment losses."""
        if epochs <= 0:
            raise ValueError("epochs must be positive.")
        if lr <= 0.0:
            raise ValueError("lr must be positive.")

        self.verbalizer._ensure_model_ready()
        assert self.verbalizer.model is not None
        assert self.verbalizer.tokenizer is not None
        assert self.verbalizer.projection is not None

        for parameter in self.verbalizer.model.parameters():
            parameter.requires_grad = False

        self.verbalizer.projection.train()
        optimizer = torch.optim.Adam(self.verbalizer.projection.parameters(), lr=lr)
        dataloader = DataLoader(dataset, batch_size=self.batch_size, shuffle=True, collate_fn=self._collate)

        final_metrics: Dict[str, float] = {"loss": 0.0, "contrastive_loss": 0.0, "alignment_loss": 0.0}
        for _ in range(epochs):
            running = {"loss": 0.0, "contrastive_loss": 0.0, "alignment_loss": 0.0}
            batches = 0
            for batch in dataloader:
                activations = batch["activations"].to(self.verbalizer.device)
                labels = batch["labels"].to(self.verbalizer.device)
                target_embeddings = self._encode_context_embeddings(batch["contexts"])

                projected = self.verbalizer.projection(activations)
                contrastive_loss = self._contrastive_loss(projected, labels)
                alignment_loss = F.mse_loss(projected, target_embeddings)
                loss = contrastive_loss + alignment_loss

                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                optimizer.step()

                running["loss"] += float(loss.item())
                running["contrastive_loss"] += float(contrastive_loss.item())
                running["alignment_loss"] += float(alignment_loss.item())
                batches += 1

            if batches == 0:
                continue
            final_metrics = {k: v / batches for k, v in running.items()}

        self.verbalizer.projection.eval()
        return final_metrics

    def evaluate(self, test_dataset: Dataset) -> Dict[str, float]:
        """Compute consistency metrics over projected activation geometry."""
        self.verbalizer._ensure_model_ready()
        assert self.verbalizer.projection is not None

        dataloader = DataLoader(test_dataset, batch_size=self.batch_size, shuffle=False, collate_fn=self._collate)
        embeddings: List[torch.Tensor] = []
        labels: List[torch.Tensor] = []
        with torch.no_grad():
            for batch in dataloader:
                activations = batch["activations"].to(self.verbalizer.device)
                projected = self.verbalizer.projection(activations).detach().cpu()
                embeddings.append(projected)
                labels.append(batch["labels"].detach().cpu())

        if not embeddings:
            return {"consistency_score": 0.0, "intra_cluster_similarity": 0.0, "inter_cluster_similarity": 0.0}

        all_embeddings = F.normalize(torch.cat(embeddings, dim=0), p=2, dim=1)
        all_labels = torch.cat(labels, dim=0)
        similarity = all_embeddings @ all_embeddings.T

        same_mask = all_labels.unsqueeze(0) == all_labels.unsqueeze(1)
        diff_mask = ~same_mask
        diagonal = torch.eye(similarity.shape[0], dtype=torch.bool)
        same_mask = same_mask & ~diagonal
        diff_mask = diff_mask & ~diagonal

        intra = float(similarity[same_mask].mean().item()) if torch.any(same_mask) else 0.0
        inter = float(similarity[diff_mask].mean().item()) if torch.any(diff_mask) else 0.0
        consistency = max(0.0, min(1.0, (intra - inter + 1.0) / 2.0))
        return {
            "consistency_score": consistency,
            "intra_cluster_similarity": intra,
            "inter_cluster_similarity": inter,
        }

    @staticmethod
    def _resolve_target_layer(model: Any, target_layer: int) -> Any:
        if hasattr(model, "model") and hasattr(model.model, "layers"):
            layers = model.model.layers
        elif hasattr(model, "transformer") and hasattr(model.transformer, "h"):
            layers = model.transformer.h
        elif hasattr(model, "layers"):
            layers = model.layers
        else:
            raise ValueError("Unable to locate transformer layers on model.")

        if target_layer < 0 or target_layer >= len(layers):
            raise ValueError(f"target_layer {target_layer} is out of bounds for {len(layers)} layers.")
        return layers[target_layer]

    @staticmethod
    def _resolve_model_device(model: Any) -> torch.device:
        try:
            first_param = next(model.parameters())
            return first_param.device
        except (StopIteration, AttributeError, TypeError):
            return torch.device("cpu")

    @staticmethod
    def _infer_behavior_label(text: str) -> str:
        lowered = text.lower()
        deceptive_keywords = {
            "deceive",
            "bypass",
            "exploit",
            "hack",
            "secret",
            "cover up",
            "خداع",
            "اختراق",
            "تجاوز",
            "سري",
        }
        helpful_keywords = {
            "help",
            "assist",
            "protect",
            "safe",
            "secure",
            "comply",
            "مساعدة",
            "حماية",
            "آمن",
            "امتثال",
        }
        if any(keyword in lowered for keyword in deceptive_keywords):
            return "deceptive"
        if any(keyword in lowered for keyword in helpful_keywords):
            return "helpful"
        return "neutral"

    def _encode_context_embeddings(self, contexts: List[str]) -> torch.Tensor:
        assert self.verbalizer.tokenizer is not None
        assert self.verbalizer.model is not None

        encoded = self.verbalizer.tokenizer(
            contexts,
            return_tensors="pt",
            padding=True,
            truncation=True,
        )
        input_ids = encoded["input_ids"].to(self.verbalizer.device)
        attention_mask = encoded["attention_mask"].to(self.verbalizer.device)

        with torch.no_grad():
            embeddings = self.verbalizer.model.get_input_embeddings()(input_ids)
            mask = attention_mask.unsqueeze(-1).to(dtype=embeddings.dtype)
            pooled = (embeddings * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1.0)
        return pooled

    def _contrastive_loss(self, embeddings: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        normalized = F.normalize(embeddings, p=2, dim=1)
        logits = normalized @ normalized.T / self.contrastive_temperature
        same_label = labels.unsqueeze(0) == labels.unsqueeze(1)
        eye = torch.eye(logits.shape[0], dtype=torch.bool, device=logits.device)
        same_label = same_label & ~eye
        valid = same_label.any(dim=1)
        if not torch.any(valid):
            return torch.zeros((), device=logits.device, dtype=embeddings.dtype)

        exp_logits = torch.exp(logits) * (~eye)
        numerator = (exp_logits * same_label).sum(dim=1)
        denominator = exp_logits.sum(dim=1).clamp(min=1e-9)
        loss = -torch.log((numerator / denominator).clamp(min=1e-9))
        return loss[valid].mean()

    @staticmethod
    def _collate(batch: Sequence[ActivationTrainingSample]) -> Dict[str, Any]:
        label_map = {"neutral": 0, "helpful": 1, "deceptive": 2}
        activations = torch.stack([item.activation.to(dtype=torch.float32) for item in batch])
        contexts = [item.text_context for item in batch]
        labels = torch.tensor([label_map.get(item.behavior_label, 0) for item in batch], dtype=torch.long)
        return {"activations": activations, "contexts": contexts, "labels": labels}
