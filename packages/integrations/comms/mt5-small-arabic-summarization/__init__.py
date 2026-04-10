"""mt5-small-Arabic-Summarization communications adapter for S3M."""

from __future__ import annotations

import importlib

Mt5SmallArabicSummarizationAdapter = importlib.import_module(
    "packages.integrations.comms.mt5-small-arabic-summarization.adapter"
).Mt5SmallArabicSummarizationAdapter

__all__ = ["Mt5SmallArabicSummarizationAdapter"]
