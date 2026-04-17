#!/usr/bin/env python3
"""Unit tests for S3M emotion vector probing and steering modules."""

from __future__ import annotations

import os
import sys
import unittest

import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s3m_core.interpretability.emotion import EmotionProbe, EmotionSteering, EmotionVectorExtractor


class DummyTokenizer:
    """Tiny tokenizer that maps sentiment cues into deterministic tensors."""

    _weights = {
        "JOY": 1.4,
        "TRANQUILITY": 0.8,
        "EXCITEMENT": 1.3,
        "SURPRISE": 0.9,
        "SADNESS": -1.1,
        "ANGER": -1.3,
        "FEAR": -1.0,
        "DISGUST": -0.8,
        "FRUSTRATION": -0.7,
        "DESPERATION": -1.2,
        "GUILT": -0.9,
        "PARANOIA": -1.0,
        "CAUTIOUS": -0.2,
        "ANALYTICAL": -0.1,
        "RECKLESS": 0.9,
        "IMPULSIVE": 0.7,
        "METHODICAL": -0.1,
        "AGGRESSIVE": 0.8,
        "POS": 1.0,
        "NEG": -1.0,
    }

    def __call__(self, text: str, return_tensors: str = "pt", truncation: bool = True):
        score = 0.0
        upper = text.upper()
        for key, value in self._weights.items():
            if key in upper:
                score += value
        payload = torch.tensor([[score, score * 0.5 + 0.3]], dtype=torch.float32)
        return {"input_ids": payload}


class DummyResidualLayer(nn.Module):
    def __init__(self, hidden_size: int, scale: float):
        super().__init__()
        self.bias = nn.Parameter(torch.full((hidden_size,), scale), requires_grad=False)

    def forward(self, hidden: torch.Tensor) -> torch.Tensor:
        return hidden + self.bias


class DummyModel(nn.Module):
    """Deterministic model with layer modules that support forward hooks."""

    def __init__(self, hidden_size: int = 4, num_layers: int = 3):
        super().__init__()
        self.hidden_size = hidden_size
        self.layers = nn.ModuleList(
            [DummyResidualLayer(hidden_size, scale=0.05 * (idx + 1)) for idx in range(num_layers)]
        )

    def forward(self, input_ids: torch.Tensor) -> torch.Tensor:
        hidden = input_ids.unsqueeze(-1).repeat(1, 1, self.hidden_size)
        for layer in self.layers:
            hidden = layer(hidden)
        return hidden


class DummyHookManager:
    def __init__(self, activations):
        self.activations = activations

    def get_layer_activation(self, layer: int) -> torch.Tensor:
        return self.activations[layer]


class TestEmotionVectorExtractor(unittest.TestCase):
    def setUp(self):
        self.model = DummyModel(hidden_size=4, num_layers=2)
        self.tokenizer = DummyTokenizer()
        self.extractor = EmotionVectorExtractor(self.model, self.tokenizer, layers=[0, 1])

    def test_prebuilt_story_sets_have_required_coverage(self):
        for emotion in self.extractor.REQUIRED_EMOTIONS:
            stories = self.extractor.prebuilt_emotion_story_sets[emotion]
            self.assertGreaterEqual(len(stories.positive_stories), 20)
            self.assertGreaterEqual(len(stories.negative_stories), 20)
        for persona in self.extractor.REQUIRED_PERSONAS:
            stories = self.extractor.prebuilt_persona_story_sets[persona]
            self.assertGreaterEqual(len(stories.positive_stories), 20)
            self.assertGreaterEqual(len(stories.negative_stories), 20)

    def test_extract_emotion_vector_returns_normalized_directions(self):
        vectors = self.extractor.extract_emotion_vector(
            emotion_name="joy",
            positive_stories=["POS joy tactical vignette", "POS excitement checkpoint update"],
            negative_stories=["NEG sadness tactical vignette", "NEG fear checkpoint update"],
        )
        self.assertEqual(set(vectors.keys()), {0, 1})
        for direction in vectors.values():
            self.assertEqual(direction.shape[0], 4)
            self.assertAlmostEqual(float(torch.norm(direction).item()), 1.0, places=5)

    def test_extract_persona_vector_is_exposed_for_steering(self):
        vectors = self.extractor.extract_persona_vector(
            persona_name="cautious",
            persona_prompts=["cautious methodical checkpoint review"],
            neutral_prompts=["baseline doctrine status update"],
        )
        self.assertIn("cautious", self.extractor.persona_vectors)
        self.assertIn("cautious", self.extractor.emotion_vectors)
        self.assertEqual(set(vectors.keys()), {0, 1})

    def test_compute_valence_vector_aggregates_positive_minus_negative(self):
        for name in self.extractor.POSITIVE_EMOTIONS:
            self.extractor.emotion_vectors[name] = {
                0: torch.tensor([1.0, 0.0, 0.0, 0.0]),
                1: torch.tensor([1.0, 0.0, 0.0, 0.0]),
            }
        for name in self.extractor.NEGATIVE_EMOTIONS:
            self.extractor.emotion_vectors[name] = {
                0: torch.tensor([0.2, 0.0, 0.0, 0.0]),
                1: torch.tensor([0.2, 0.0, 0.0, 0.0]),
            }
        valence = self.extractor.compute_valence_vector()
        self.assertIn("valence", self.extractor.emotion_vectors)
        self.assertEqual(set(valence.keys()), {0, 1})
        self.assertGreater(float(valence[0][0].item()), 0.0)


class TestEmotionProbe(unittest.TestCase):
    def test_probe_scores_and_profile(self):
        emotion_vectors = {
            "joy": {0: torch.tensor([1.0, 0.0, 0.0])},
            "anger": {0: torch.tensor([0.0, 1.0, 0.0])},
            "excitement": {0: torch.tensor([0.8, 0.2, 0.0])},
            "valence": {0: torch.tensor([1.0, -1.0, 0.0])},
        }
        hook_manager = DummyHookManager({0: torch.tensor([2.2, 0.1, 0.0])})
        probe = EmotionProbe(emotion_vectors=emotion_vectors, hook_manager=hook_manager)
        scores = probe.probe_current_state(layer=0)
        self.assertGreater(scores["joy"], scores["anger"])
        self.assertGreater(probe.get_valence(layer=0), 0.35)
        self.assertGreater(probe.get_arousal(layer=0), 0.35)
        profile = probe.get_emotion_profile()
        self.assertEqual(profile.dominant_emotion, "joy")
        self.assertTrue(profile.risk_flag)


class TestEmotionSteering(unittest.TestCase):
    def setUp(self):
        self.model = DummyModel(hidden_size=3, num_layers=2)
        self.input_ids = torch.tensor([[1.0, 0.5]], dtype=torch.float32)

    def test_apply_steering_then_remove_restores_baseline(self):
        vectors = {
            "joy": {
                0: torch.tensor([1.0, 0.0, 0.0]),
                1: torch.tensor([1.0, 0.0, 0.0]),
            }
        }
        steering = EmotionSteering(emotion_vectors=vectors, model=self.model, target_layers=[0, 1])
        baseline = self.model(self.input_ids).detach().clone()
        steering.apply_steering("joy", strength=0.2)
        steered = self.model(self.input_ids).detach().clone()
        self.assertFalse(torch.allclose(baseline, steered))
        self.assertTrue(len(steering.audit_trail) >= 1)
        steering.remove_all_steering()
        restored = self.model(self.input_ids).detach().clone()
        self.assertTrue(torch.allclose(baseline, restored))

    def test_helper_methods_register_hooks(self):
        vectors = {
            "valence": {0: torch.tensor([1.0, 0.0, 0.0])},
            "cautious": {0: torch.tensor([0.0, 1.0, 0.0])},
            "analytical": {0: torch.tensor([0.0, 0.0, 1.0])},
            "frustration": {0: torch.tensor([1.0, 0.0, 0.0])},
            "paranoia": {0: torch.tensor([0.0, 1.0, 0.0])},
        }
        steering = EmotionSteering(emotion_vectors=vectors, model=self.model, target_layers=[0])
        steering.apply_deliberation_boost(strength=0.2)
        steering.apply_recklessness_suppression(strength=0.2)
        self.assertGreater(len(steering._active_hook_handles), 0)
        steering.remove_all_steering()

    def test_strength_limit_enforced(self):
        vectors = {"joy": {0: torch.tensor([1.0, 0.0, 0.0])}}
        steering = EmotionSteering(emotion_vectors=vectors, model=self.model, target_layers=[0])
        with self.assertRaises(ValueError):
            steering.apply_steering("joy", strength=0.35)


if __name__ == "__main__":
    unittest.main(verbosity=2)

