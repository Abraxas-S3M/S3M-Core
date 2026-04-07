"""S3M Training Dataset Builder — Converts S3M scenario data to training-ready JSONL.

Sources:
  - configs/training/{saudi_mod,ukraine_mod,nato}.yaml scenario packs
  - data/osint/ intelligence reports
  - Manual instruction sets (data/datasets/raw/)

Output format (JSONL):
  {"prompt": "...", "completion": "...", "engine": "phi3", "domain": "tactical", "lang": "en"}

For ALLaM Arabic bilingual:
  {"prompt": "...", "completion": "...", "engine": "allam", "domain": "arabic_nlp", "lang": "ar"}
  {"prompt": "...", "completion": "...", "engine": "allam", "domain": "arabic_nlp", "lang": "mixed"}
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger("s3m.training.gpu.dataset_builder")


# ── S3M Domain Templates ────────────────────────────────────────────────

TACTICAL_TEMPLATES = [
    {
        "prompt": "Generate a SITREP for the current operational area. Friendly forces: {friendly}. Enemy activity: {enemy}. Weather: {weather}.",
        "domain": "tactical",
        "engine": "phi3",
    },
    {
        "prompt": "Assess the threat level for sector {sector}. Known threats: {threats}. ROE status: {roe}.",
        "domain": "tactical",
        "engine": "phi3",
    },
]

PLANNING_TEMPLATES = [
    {
        "prompt": "Create a logistics plan for moving {units} from {origin} to {destination}. Available transport: {transport}. Timeline: {timeline}.",
        "domain": "planning",
        "engine": "mistral",
    },
    {
        "prompt": "Generate an OPORD for {mission_type}. Phase 1: {phase1}. Phase 2: {phase2}. Commander's intent: {intent}.",
        "domain": "planning",
        "engine": "mistral",
    },
]

REASONING_TEMPLATES = [
    {
        "prompt": "Analyze the strategic implications of {event}. Consider: regional stability, GCC alliance, maritime security, and energy infrastructure. Provide a structured assessment.",
        "domain": "reasoning",
        "engine": "grok",
    },
]

ARABIC_TEMPLATES = [
    {
        "prompt": "قم بإعداد تقرير موقف عن القطاع {sector}. القوات الصديقة: {friendly}. نشاط العدو: {enemy}.",
        "domain": "arabic_nlp",
        "engine": "allam",
        "lang": "ar",
    },
    {
        "prompt": "ترجم التقرير التالي إلى العربية مع الحفاظ على المصطلحات العسكرية:\n{english_text}",
        "domain": "arabic_nlp",
        "engine": "allam",
        "lang": "mixed",
    },
    {
        "prompt": "Translate the following military SITREP to Arabic, preserving tactical terminology:\n{english_text}",
        "domain": "arabic_nlp",
        "engine": "allam",
        "lang": "mixed",
    },
]


class DatasetBuilder:
    """Build S3M fine-tuning datasets from scenario configs and templates."""

    def __init__(self, output_dir: str = "data/datasets") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_from_scenarios(
        self,
        scenarios_dir: str = "configs/training",
        engine_filter: Optional[str] = None,
    ) -> Dict[str, str]:
        """Convert scenario YAML files to per-engine JSONL datasets."""
        scenario_dir = Path(scenarios_dir)
        outputs = {}

        for yaml_path in scenario_dir.glob("*.yaml"):
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
            except Exception:
                continue

            track = yaml_path.stem
            scenarios = data.get("scenarios", data.get("training", {}).get("scenarios", []))
            if not isinstance(scenarios, list):
                continue

            for scenario in scenarios:
                if not isinstance(scenario, dict):
                    continue
                prompt = scenario.get("prompt", scenario.get("input", ""))
                completion = scenario.get("completion", scenario.get("output", scenario.get("expected", "")))
                domain = scenario.get("domain", track)
                engine = scenario.get("engine", self._domain_to_engine(domain))
                lang = scenario.get("lang", "en")

                if engine_filter and engine != engine_filter:
                    continue

                entry = {
                    "prompt": str(prompt),
                    "completion": str(completion),
                    "engine": engine,
                    "domain": domain,
                    "lang": lang,
                    "source": f"scenario:{track}",
                    "id": f"s3m-{uuid.uuid4().hex[:8]}",
                }

                engine_file = self.output_dir / f"s3m_{engine}_instruct.jsonl"
                with engine_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

                if engine not in outputs:
                    outputs[engine] = str(engine_file)

        logger.info("Built datasets: %s", {k: str(v) for k, v in outputs.items()})
        return outputs

    def build_arabic_bilingual(
        self,
        english_dataset: str,
        output_name: str = "s3m_allam_bilingual.jsonl",
    ) -> str:
        """Create bilingual dataset for ALLaM by augmenting English data with Arabic templates."""
        output_path = self.output_dir / output_name
        count = 0

        en_path = Path(english_dataset)
        if en_path.exists():
            for line in en_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Create Arabic translation instruction pair
                bilingual = {
                    "prompt": f"ترجم هذا التقرير العسكري إلى العربية:\n{entry.get('prompt', '')}",
                    "completion": entry.get("completion", ""),
                    "engine": "allam",
                    "domain": "arabic_nlp",
                    "lang": "mixed",
                    "source": f"bilingual:{en_path.stem}",
                    "id": f"s3m-ar-{uuid.uuid4().hex[:8]}",
                }

                with output_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(bilingual, ensure_ascii=False) + "\n")
                count += 1

        logger.info("Built Arabic bilingual dataset: %d pairs → %s", count, output_path)
        return str(output_path)

    @staticmethod
    def _domain_to_engine(domain: str) -> str:
        mapping = {
            "tactical": "phi3",
            "planning": "mistral",
            "reasoning": "grok",
            "arabic_nlp": "allam",
            "arabic": "allam",
        }
        return mapping.get(domain, "phi3")


class TokenizationValidator:
    """Validate that training data tokenizes correctly for each engine."""

    def __init__(self) -> None:
        self._tokenizers = {}

    def validate_dataset(
        self,
        dataset_path: str,
        engine_id: str,
        max_seq_length: int = 4096,
        sample_size: int = 100,
    ) -> Dict[str, Any]:
        """Check tokenization stats and flag issues."""
        path = Path(dataset_path)
        if not path.exists():
            return {"error": f"Dataset not found: {dataset_path}"}

        try:
            from transformers import AutoTokenizer
        except ImportError:
            return {"error": "transformers not installed"}

        from src.training.gpu.config import GPUTrainingConfig
        config = GPUTrainingConfig.from_yaml()
        engine_cfg = config.engines.get(engine_id)
        if not engine_cfg:
            return {"error": f"Unknown engine: {engine_id}"}

        tokenizer = AutoTokenizer.from_pretrained(engine_cfg.hf_repo, trust_remote_code=True)

        lengths = []
        truncated = 0
        arabic_count = 0
        total = 0

        for line in path.read_text(encoding="utf-8").splitlines()[:sample_size]:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            text = f"{entry.get('prompt', '')} {entry.get('completion', '')}"
            tokens = tokenizer.encode(text)
            lengths.append(len(tokens))
            if len(tokens) > max_seq_length:
                truncated += 1
            if any("\u0600" <= ch <= "\u06FF" for ch in text[:200]):
                arabic_count += 1
            total += 1

        return {
            "engine": engine_id,
            "samples_checked": total,
            "avg_tokens": round(sum(lengths) / max(1, len(lengths)), 1),
            "max_tokens": max(lengths) if lengths else 0,
            "min_tokens": min(lengths) if lengths else 0,
            "truncated_count": truncated,
            "truncation_rate": round(truncated / max(1, total), 3),
            "arabic_samples": arabic_count,
            "max_seq_length": max_seq_length,
        }
