"""Normalization helpers for Hugging Face model and inference payloads."""

from __future__ import annotations

from typing import Any


class HuggingFaceNormalizer:
    def infer_task(self, model_id: str) -> str:
        model_lower = model_id.lower()
        if "whisper" in model_lower:
            return "automatic-speech-recognition"
        if "yolo" in model_lower or "detect" in model_lower:
            return "object-detection"
        if "mt5" in model_lower or "xlsum" in model_lower:
            return "summarization"
        if "arabert" in model_lower or "camelbert" in model_lower or "bert" in model_lower:
            return "fill-mask"
        return "text-generation"

    def normalize_model_info(self, info: dict[str, Any]) -> dict[str, Any]:
        languages = [tag.split(":", 1)[1] for tag in info.get("tags", []) if isinstance(tag, str) and tag.startswith("language:")]
        framework = next((tag.split(":", 1)[1] for tag in info.get("tags", []) if isinstance(tag, str) and tag.startswith("library:")), "unknown")
        return {
            "model_id": info.get("model_id", ""),
            "provider": "huggingface",
            "task": info.get("pipeline_tag", info.get("task", "unknown")),
            "framework": framework,
            "size_mb": float(info.get("size_mb", 0.0)),
            "languages": languages,
            "tags": info.get("tags", []),
            "locally_available": bool(info.get("locally_cached", False)),
            "quantization": info.get("quantization"),
            "s3m_layer": info.get("s3m_layer"),
        }

    def normalize_inference_result(self, result: dict[str, Any], task: str) -> dict[str, Any]:
        payload = result.get("result")
        if task == "text-generation":
            if isinstance(payload, list) and payload:
                return {"generated_text": payload[0].get("generated_text", "")}
            if isinstance(payload, dict):
                return {"generated_text": payload.get("generated_text", "")}
            return {"generated_text": str(payload or "")}

        if task == "summarization":
            if isinstance(payload, list) and payload:
                return {"summary": payload[0].get("summary_text", "")}
            if isinstance(payload, dict):
                return {"summary": payload.get("summary_text", payload.get("summary", ""))}
            return {"summary": str(payload or "")}

        if task == "fill-mask":
            if isinstance(payload, list):
                return {"predictions": payload}
            return {"predictions": []}

        if task == "object-detection":
            if isinstance(payload, list):
                return {"detections": payload}
            return {"detections": []}

        if task == "automatic-speech-recognition":
            if isinstance(payload, dict):
                return {"transcription": payload.get("text", payload.get("transcription", ""))}
            return {"transcription": str(payload or "")}

        return {"result": payload}
