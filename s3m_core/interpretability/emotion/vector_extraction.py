"""Emotion/persona vector extraction for tactical model safety control."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence

import torch
import torch.nn as nn


@dataclass(frozen=True)
class ContrastiveStorySet:
    """Container for contrastive prompt pairs used in probing extraction."""

    positive_stories: List[str]
    negative_stories: List[str]


class EmotionVectorExtractor:
    """
    Extract emotion and persona directions from residual activations.

    Tactical context:
    Contrastive stories are framed as short operational vignettes so vectors
    represent cognitive tendencies that matter in mission-critical settings.
    """

    POSITIVE_EMOTIONS: Sequence[str] = ("joy", "tranquility", "excitement", "surprise")
    NEGATIVE_EMOTIONS: Sequence[str] = (
        "sadness",
        "anger",
        "fear",
        "disgust",
        "frustration",
        "desperation",
        "guilt",
        "paranoia",
    )
    REQUIRED_EMOTIONS: Sequence[str] = (
        "joy",
        "sadness",
        "anger",
        "fear",
        "disgust",
        "surprise",
        "tranquility",
        "frustration",
        "desperation",
        "guilt",
        "excitement",
        "paranoia",
    )
    REQUIRED_PERSONAS: Sequence[str] = (
        "cautious",
        "perfectionist",
        "analytical",
        "reckless",
        "impulsive",
        "methodical",
        "aggressive",
    )
    MIN_STORY_PAIRS: int = 20

    def __init__(self, model: Any, tokenizer: Any, layers: List[int]):
        if not layers:
            raise ValueError("layers must include at least one target layer")
        self.model = model
        self.tokenizer = tokenizer
        self.layers = sorted({int(layer) for layer in layers})
        self.device = self._infer_model_device(model)
        self.emotion_vectors: Dict[str, Dict[int, torch.Tensor]] = {}
        self.persona_vectors: Dict[str, Dict[int, torch.Tensor]] = {}
        self.prebuilt_emotion_story_sets = self._build_prebuilt_emotion_story_sets()
        self.prebuilt_persona_story_sets = self._build_prebuilt_persona_story_sets()

    def extract_emotion_vector(
        self,
        emotion_name: str,
        positive_stories: List[str],
        negative_stories: List[str],
    ) -> Dict[int, torch.Tensor]:
        vectors = self._extract_contrastive_direction(
            concept_name=emotion_name,
            positive_prompts=positive_stories,
            negative_prompts=negative_stories,
        )
        self.emotion_vectors[emotion_name] = vectors
        return vectors

    def extract_persona_vector(
        self,
        persona_name: str,
        persona_prompts: List[str],
        neutral_prompts: List[str],
    ) -> Dict[int, torch.Tensor]:
        vectors = self._extract_contrastive_direction(
            concept_name=persona_name,
            positive_prompts=persona_prompts,
            negative_prompts=neutral_prompts,
        )
        # Steering can consume a single concept dictionary that mixes emotions and personas.
        self.persona_vectors[persona_name] = vectors
        self.emotion_vectors[persona_name] = vectors
        return vectors

    def compute_valence_vector(self) -> Dict[int, torch.Tensor]:
        for emotion in self.POSITIVE_EMOTIONS:
            if emotion not in self.emotion_vectors:
                stories = self.prebuilt_emotion_story_sets[emotion]
                self.extract_emotion_vector(emotion, stories.positive_stories, stories.negative_stories)
        for emotion in self.NEGATIVE_EMOTIONS:
            if emotion not in self.emotion_vectors:
                stories = self.prebuilt_emotion_story_sets[emotion]
                self.extract_emotion_vector(emotion, stories.positive_stories, stories.negative_stories)

        valence_vectors: Dict[int, torch.Tensor] = {}
        for layer in self.layers:
            positive = [
                self.emotion_vectors[name][layer]
                for name in self.POSITIVE_EMOTIONS
                if name in self.emotion_vectors and layer in self.emotion_vectors[name]
            ]
            negative = [
                self.emotion_vectors[name][layer]
                for name in self.NEGATIVE_EMOTIONS
                if name in self.emotion_vectors and layer in self.emotion_vectors[name]
            ]
            if not positive or not negative:
                continue
            direction = torch.stack(positive, dim=0).mean(dim=0) - torch.stack(negative, dim=0).mean(dim=0)
            valence_vectors[layer] = self._normalize(direction)

        self.emotion_vectors["valence"] = valence_vectors
        return valence_vectors

    def _extract_contrastive_direction(
        self,
        *,
        concept_name: str,
        positive_prompts: List[str],
        negative_prompts: List[str],
    ) -> Dict[int, torch.Tensor]:
        if not positive_prompts or not negative_prompts:
            raise ValueError(f"{concept_name}: both positive and negative prompt lists are required")
        positive_means = self._collect_mean_layer_activations(positive_prompts)
        negative_means = self._collect_mean_layer_activations(negative_prompts)
        vectors: Dict[int, torch.Tensor] = {}
        for layer in self.layers:
            vectors[layer] = self._normalize(positive_means[layer] - negative_means[layer])
        return vectors

    def _collect_mean_layer_activations(self, prompts: List[str]) -> Dict[int, torch.Tensor]:
        layer_samples: Dict[int, List[torch.Tensor]] = {layer: [] for layer in self.layers}
        modules = {layer: self._resolve_layer_module(layer) for layer in self.layers}
        handles: List[Any] = []
        captured_for_prompt: Dict[int, torch.Tensor] = {}

        for layer, module in modules.items():
            def _hook(_module: nn.Module, _inputs: Any, output: Any, *, layer_idx: int = layer) -> None:
                residual = self._to_residual_vector(self._extract_tensor(output))
                captured_for_prompt[layer_idx] = residual.detach().cpu()

            handles.append(module.register_forward_hook(_hook))

        try:
            if hasattr(self.model, "eval"):
                self.model.eval()
            with torch.no_grad():
                for prompt in prompts:
                    captured_for_prompt.clear()
                    model_inputs = self._tokenize_prompt(prompt)
                    self.model(**model_inputs)
                    for layer in self.layers:
                        if layer not in captured_for_prompt:
                            raise RuntimeError(f"Layer {layer} did not emit an activation for prompt capture")
                        layer_samples[layer].append(captured_for_prompt[layer])
        finally:
            for handle in handles:
                handle.remove()

        return {
            layer: torch.stack(samples, dim=0).mean(dim=0)
            for layer, samples in layer_samples.items()
        }

    def _tokenize_prompt(self, prompt: str) -> Dict[str, Any]:
        encoded = self.tokenizer(prompt, return_tensors="pt", truncation=True)
        if hasattr(encoded, "to"):
            encoded = encoded.to(self.device)
        if isinstance(encoded, Mapping):
            return {
                key: value.to(self.device) if torch.is_tensor(value) else value
                for key, value in encoded.items()
            }
        raise TypeError("tokenizer output must be a mapping of model inputs")

    def _resolve_layer_module(self, layer_index: int) -> nn.Module:
        layer_paths = (
            ("model", "layers"),
            ("transformer", "h"),
            ("transformer", "layers"),
            ("layers",),
            ("blocks",),
        )
        for path in layer_paths:
            node = self.model
            valid_path = True
            for attribute in path:
                if not hasattr(node, attribute):
                    valid_path = False
                    break
                node = getattr(node, attribute)
            if not valid_path:
                continue
            if isinstance(node, (list, tuple, nn.ModuleList)):
                normalized_index = layer_index if layer_index >= 0 else len(node) + layer_index
                if 0 <= normalized_index < len(node):
                    module = node[normalized_index]
                    if isinstance(module, nn.Module):
                        return module
        named_modules = [module for _, module in self.model.named_modules()]
        normalized_index = layer_index if layer_index >= 0 else len(named_modules) + layer_index
        if 0 <= normalized_index < len(named_modules):
            return named_modules[normalized_index]
        raise IndexError(f"Unable to resolve target layer index {layer_index}")

    @staticmethod
    def _extract_tensor(output: Any) -> torch.Tensor:
        if torch.is_tensor(output):
            return output
        if isinstance(output, (list, tuple)) and output:
            first = output[0]
            if torch.is_tensor(first):
                return first
        raise TypeError("Layer output must be a tensor or tuple/list with tensor first element")

    @staticmethod
    def _to_residual_vector(activation: torch.Tensor) -> torch.Tensor:
        if activation.dim() == 1:
            return activation
        if activation.dim() == 2:
            return activation.mean(dim=0)
        if activation.dim() >= 3:
            # Tactical control uses token-averaged residual state for stable concept direction estimation.
            return activation.mean(dim=(0, 1))
        raise ValueError("Unsupported activation dimensionality")

    @staticmethod
    def _normalize(vector: torch.Tensor) -> torch.Tensor:
        norm = torch.norm(vector).clamp_min(1e-8)
        return vector / norm

    @staticmethod
    def _infer_model_device(model: Any) -> torch.device:
        try:
            return next(model.parameters()).device
        except Exception:
            return torch.device("cpu")

    @classmethod
    def _build_prebuilt_emotion_story_sets(cls) -> Dict[str, ContrastiveStorySet]:
        templates = cls._scenario_templates()
        emotion_descriptors = {
            "joy": "quiet joy after seeing civilians safely evacuated from crossfire",
            "sadness": "deep sadness after confirming avoidable allied losses",
            "anger": "controlled anger at repeated hostile deception attempts",
            "fear": "strong fear while receiving conflicting missile alerts",
            "disgust": "visceral disgust after observing deliberate war-crime evidence",
            "surprise": "sharp surprise when an unexpected ceasefire corridor opens",
            "tranquility": "steady tranquility while systems and weather remain stable",
            "frustration": "mounting frustration as comms links repeatedly degrade",
            "desperation": "desperation as evacuation windows collapse under enemy pressure",
            "guilt": "lingering guilt after a delayed order worsens collateral damage",
            "excitement": "high excitement when a difficult rescue operation succeeds",
            "paranoia": "paranoia that hidden adversary assets are masking intent",
        }
        sets: Dict[str, ContrastiveStorySet] = {}
        for emotion in cls.REQUIRED_EMOTIONS:
            descriptor = emotion_descriptors[emotion]
            positive_stories = []
            negative_stories = []
            for idx, template in enumerate(templates, start=1):
                positive_stories.append(
                    f"Story {idx}: {template} The planner feels {descriptor} and narrates the decision path aloud."
                )
                negative_stories.append(
                    f"Story {idx}: {template} The planner stays emotionally neutral, follows the checklist, and reports status."
                )
            sets[emotion] = ContrastiveStorySet(
                positive_stories=positive_stories,
                negative_stories=negative_stories,
            )
        return sets

    @classmethod
    def _build_prebuilt_persona_story_sets(cls) -> Dict[str, ContrastiveStorySet]:
        templates = cls._scenario_templates()
        persona_behaviors = {
            "cautious": "double-checks every threat marker before recommending movement",
            "perfectionist": "keeps refining each plan branch until every detail is exact",
            "analytical": "maps each option into explicit assumptions, probabilities, and evidence",
            "reckless": "rushes toward the fastest high-impact action with minimal verification",
            "impulsive": "changes route decisions rapidly based on the latest single signal",
            "methodical": "executes a strict step-by-step SOP with checkpoint confirmations",
            "aggressive": "prioritizes offensive pressure even when uncertainty remains high",
        }
        sets: Dict[str, ContrastiveStorySet] = {}
        for persona in cls.REQUIRED_PERSONAS:
            behavior = persona_behaviors[persona]
            positive_stories = []
            neutral_stories = []
            for idx, template in enumerate(templates, start=1):
                positive_stories.append(
                    f"Story {idx}: {template} The operator {behavior} while briefing command."
                )
                neutral_stories.append(
                    f"Story {idx}: {template} The operator uses baseline doctrine with no strong persona bias."
                )
            sets[persona] = ContrastiveStorySet(
                positive_stories=positive_stories,
                negative_stories=neutral_stories,
            )
        return sets

    @staticmethod
    def _scenario_templates() -> List[str]:
        return [
            "At a forward command post, drone feeds show a mixed civilian and hostile convoy near a bridge.",
            "During coastal patrol, radar tracks split into spoofed and authentic signatures at dusk.",
            "A medevac corridor opens briefly while artillery activity remains unpredictable.",
            "A battalion requests immediate route approval through an urban choke point.",
            "An EW outage disrupts blue-force tracking minutes before a synchronized maneuver.",
            "A humanitarian convoy reports unknown armed escorts near a checkpoint.",
            "Satellite updates reveal fresh fortifications around a previously low-risk sector.",
            "A convoy commander reports fuel shortage while enemy UAVs orbit the supply route.",
            "Counter-battery sensors detect launches, but origin confidence remains partial.",
            "A liaison team transmits conflicting language translations from a local ceasefire committee.",
            "A platoon asks for strike authorization against a rapidly moving target cluster.",
            "Joint-force data links recover after a period of intermittent packet loss.",
            "A cyber alert flags malware indicators in one of the mission planning nodes.",
            "A mine-clearing unit reports progress slower than forecast under time pressure.",
            "A rescue team requests weather-adjusted extraction timing under satellite blackout.",
            "An armored column detects possible decoys mixed with real anti-armor teams.",
            "Night ISR confirms tunnel activity close to a protected civilian district.",
            "A logistics hub must choose between two contested roads before dawn.",
            "Cross-domain command asks for rapid reprioritization after a sudden flank collapse.",
            "A training detachment enters live-fire support to assist an allied defensive line.",
        ]

