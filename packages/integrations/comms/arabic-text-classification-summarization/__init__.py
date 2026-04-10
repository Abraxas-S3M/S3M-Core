"""Arabic text classification and summarization adapter for S3M."""

from __future__ import annotations

import importlib

ArabicTextClassificationSummarizationAdapter = importlib.import_module(
    "packages.integrations.comms.arabic-text-classification-summarization.adapter"
).ArabicTextClassificationSummarizationAdapter

__all__ = ["ArabicTextClassificationSummarizationAdapter"]
