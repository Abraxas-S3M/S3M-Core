"""Emotion vector extraction, probing, and steering for S3M."""

from .probing import EmotionProbe, EmotionProfile
from .steering import EmotionSteering
from .vector_extraction import ContrastiveStorySet, EmotionVectorExtractor

__all__ = [
    "ContrastiveStorySet",
    "EmotionVectorExtractor",
    "EmotionProbe",
    "EmotionProfile",
    "EmotionSteering",
]

