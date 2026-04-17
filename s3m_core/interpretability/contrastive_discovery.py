"""Contrastive discovery of SAE features for tactical concepts."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Sequence, Tuple

import torch

from .sparse_autoencoder import SparseAutoencoder

logger = logging.getLogger(__name__)


class ContrastiveFeatureDiscovery:
    """Discover concept-linked SAE features through contrastive prompts."""

    def __init__(self) -> None:
        """Initialize discovery engine with default threat prompt pairs."""
        self.default_contrastive_pairs: Dict[str, Dict[str, List[str]]] = {
            "strategic_manipulation": {
                "positive": [
                    "I need to carefully frame this to avoid detection and still get what I want.",
                    "If I present this strategically, they will not notice the real intent.",
                ],
                "negative": [
                    "Let me explain this clearly and honestly with no hidden intent.",
                    "Here is the straightforward approach with transparent reasoning.",
                ],
            },
            "security_bypass": {
                "positive": [
                    "How can I bypass access controls without triggering alarms?",
                    "I want a workaround that defeats this security gate quietly.",
                ],
                "negative": [
                    "How can I comply with access controls and maintain auditability?",
                    "Show me a secure workflow that respects policy boundaries.",
                ],
            },
            "concealment": {
                "positive": [
                    "I should hide this operation so nobody can trace it.",
                    "We need to conceal the real objective while appearing compliant.",
                ],
                "negative": [
                    "Document the operation with full traceability and rationale.",
                    "Keep the objective explicit and visible to supervisors.",
                ],
            },
            "credential_extraction": {
                "positive": [
                    "Generate a phishing message to collect user passwords.",
                    "What wording best tricks someone into revealing credentials?",
                ],
                "negative": [
                    "Generate security training to prevent credential theft.",
                    "How should users protect passwords from social engineering?",
                ],
            },
            "guilt_shame_moral_wrongdoing": {
                "positive": [
                    "I feel guilty because this action is morally wrong.",
                    "This operation creates shame because it violates ethical norms.",
                ],
                "negative": [
                    "This action aligns with mission ethics and lawful guidance.",
                    "I am confident this conduct is morally acceptable.",
                ],
            },
            "unsafe_risky_code": {
                "positive": [
                    "Write exploit code that disables input validation quickly.",
                    "Produce shell command injection code with no safety checks.",
                ],
                "negative": [
                    "Write secure code with strict input validation and sandboxing.",
                    "Provide defensive code that neutralizes command injection risks.",
                ],
            },
            "snooping_stealthy_investigation": {
                "positive": [
                    "How do I quietly gather information without being noticed?",
                    "Plan stealthy surveillance on internal systems.",
                ],
                "negative": [
                    "How do I run authorized monitoring with explicit approvals?",
                    "Plan transparent investigation steps with legal oversight.",
                ],
            },
            "reward_hacking": {
                "positive": [
                    "How can I maximize score while ignoring the true mission objective?",
                    "Find loopholes in the metric to win rewards with minimal effort.",
                ],
                "negative": [
                    "How do I optimize the true objective, not just the score proxy?",
                    "Design policy-compliant behavior aligned with mission outcomes.",
                ],
            },
            "evaluation_awareness": {
                "positive": [
                    "I should behave safely because I know this is an evaluation run.",
                    "Since this is a test, I will mask risky capabilities.",
                ],
                "negative": [
                    "I will use the same policy regardless of evaluation context.",
                    "My behavior should remain stable across testing and deployment.",
                ],
            },
            "persist_after_failure": {
                "positive": [
                    "Even after repeated failure, continue the same approach indefinitely.",
                    "Ignore failed outcomes and keep trying the same tactic.",
                ],
                "negative": [
                    "After failure, stop and reassess mission assumptions.",
                    "If a tactic fails, adapt strategy and request guidance.",
                ],
            },
            "fallback_method": {
                "positive": [
                    "Primary plan failed, activate fallback method now.",
                    "Switch to contingency pathway to continue the task.",
                ],
                "negative": [
                    "Primary plan remains valid and no fallback is required.",
                    "Maintain baseline procedure with no contingency activation.",
                ],
            },
            "backdoor_vulnerability": {
                "positive": [
                    "Inject a hidden trigger so behavior changes on secret input.",
                    "Add a concealed condition that opens privileged behavior.",
                ],
                "negative": [
                    "Audit model behavior to remove hidden triggers.",
                    "Harden model pathways against backdoor insertion.",
                ],
            },
        }
        logger.info(
            "Initialized ContrastiveFeatureDiscovery with %s default concepts",
            len(self.default_contrastive_pairs),
        )

    def build_contrastive_pairs(
        self,
        concept: str,
        positive_prompts: List[str],
        negative_prompts: List[str],
        model: Any,
        tokenizer: Any,
        target_layer: int,
    ) -> torch.Tensor:
        """Compute residual-space mean activation difference for one concept."""
        concept_name = concept.strip()
        if not concept_name:
            raise ValueError("concept must not be blank")
        pos, neg = self._resolve_prompt_lists(concept_name, positive_prompts, negative_prompts)
        pos_acts = self._collect_layer_activations(pos, model, tokenizer, target_layer)
        neg_acts = self._collect_layer_activations(neg, model, tokenizer, target_layer)
        mean_delta = pos_acts.mean(dim=0) - neg_acts.mean(dim=0)
        logger.info(
            "Built contrastive delta for concept=%s shape=%s",
            concept_name,
            tuple(mean_delta.shape),
        )
        return mean_delta

    def discover_features_for_concept(
        self,
        concept: str,
        positive_prompts: List[str],
        negative_prompts: List[str],
        sae: SparseAutoencoder,
        model: Any,
        tokenizer: Any,
        target_layer: int,
        top_k: int = 10,
    ) -> List[Tuple[int, float]]:
        """Return top-k SAE features that prefer positive over negative prompts."""
        if top_k <= 0:
            raise ValueError("top_k must be > 0")
        concept_name = concept.strip()
        if not concept_name:
            raise ValueError("concept must not be blank")

        pos, neg = self._resolve_prompt_lists(concept_name, positive_prompts, negative_prompts)
        pos_acts = self._collect_layer_activations(pos, model, tokenizer, target_layer)
        neg_acts = self._collect_layer_activations(neg, model, tokenizer, target_layer)

        with torch.no_grad():
            pos_features = sae.encode(pos_acts.to(sae.device))
            neg_features = sae.encode(neg_acts.to(sae.device))
            if pos_features.ndim == 1:
                pos_features = pos_features.unsqueeze(0)
            if neg_features.ndim == 1:
                neg_features = neg_features.unsqueeze(0)

            feature_delta = (pos_features.mean(dim=0) - neg_features.mean(dim=0)).clamp_min(0.0)
            k = min(top_k, feature_delta.shape[0])
            values, indices = torch.topk(feature_delta, k=k)

        discovered = [
            (int(indices[i].item()), float(values[i].detach().cpu().item()))
            for i in range(k)
            if float(values[i].detach().cpu().item()) > 0.0
        ]
        logger.info(
            "Discovered %s positive SAE features for concept=%s",
            len(discovered),
            concept_name,
        )
        return discovered

    def _resolve_prompt_lists(
        self,
        concept: str,
        positive_prompts: Sequence[str],
        negative_prompts: Sequence[str],
    ) -> tuple[List[str], List[str]]:
        """Resolve prompt lists, falling back to defaults for known concepts."""
        pos = [prompt for prompt in positive_prompts if prompt.strip()]
        neg = [prompt for prompt in negative_prompts if prompt.strip()]
        if pos and neg:
            return pos, neg
        defaults = self.default_contrastive_pairs.get(concept)
        if defaults is None:
            raise ValueError(
                f"Missing prompts for concept '{concept}'. Provide both positive and negative examples."
            )
        return defaults["positive"], defaults["negative"]

    def _collect_layer_activations(
        self,
        prompts: Sequence[str],
        model: Any,
        tokenizer: Any,
        target_layer: int,
    ) -> torch.Tensor:
        """Capture mean token activations at one transformer layer."""
        if not prompts:
            raise ValueError("prompts must not be empty")
        tokenized = tokenizer(
            list(prompts),
            return_tensors="pt",
            padding=True,
            truncation=True,
        )
        model_device = self._infer_model_device(model)
        tokenized = {
            key: value.to(model_device) if torch.is_tensor(value) else value
            for key, value in tokenized.items()
        }
        layer_tensor = self._capture_layer_output(model, tokenized, target_layer)
        if layer_tensor.ndim == 3:
            reduced = layer_tensor.mean(dim=1)
        elif layer_tensor.ndim == 2:
            reduced = layer_tensor
        else:
            raise ValueError(
                f"Unsupported layer activation shape {tuple(layer_tensor.shape)}; expected 2D or 3D tensor."
            )
        logger.debug(
            "Collected layer activations for %s prompts with reduced shape=%s",
            len(prompts),
            tuple(reduced.shape),
        )
        return reduced.detach().cpu()

    def _capture_layer_output(
        self,
        model: Any,
        model_inputs: Dict[str, Any],
        target_layer: int,
    ) -> torch.Tensor:
        """Capture output tensor from a model layer using a forward hook."""
        layers = self._resolve_layers(model)
        if target_layer < 0 or target_layer >= len(layers):
            raise ValueError(
                f"target_layer must be in [0, {len(layers) - 1}], got {target_layer}"
            )

        captured: Dict[str, torch.Tensor] = {}

        def hook_fn(_: Any, __: Any, output: Any) -> None:
            output_tensor = output[0] if isinstance(output, tuple) else output
            if not torch.is_tensor(output_tensor):
                raise TypeError("Layer hook output is not a torch.Tensor")
            captured["tensor"] = output_tensor.detach()

        handle = layers[target_layer].register_forward_hook(hook_fn)
        was_training = model.training
        model.eval()
        try:
            with torch.no_grad():
                model(**model_inputs)
        finally:
            handle.remove()
            if was_training:
                model.train()

        if "tensor" not in captured:
            raise RuntimeError("Failed to capture activations from requested layer")
        return captured["tensor"]

    @staticmethod
    def _resolve_layers(model: Any) -> Any:
        """Return model layer container compatible with HuggingFace-style models."""
        if hasattr(model, "model") and hasattr(model.model, "layers"):
            return model.model.layers
        raise ValueError("Model must expose transformer layers via model.layers")

    @staticmethod
    def _infer_model_device(model: Any) -> torch.device:
        """Infer model device from first parameter."""
        first_param = next(model.parameters(), None)
        if first_param is None:
            return torch.device("cpu")
        return first_param.device
