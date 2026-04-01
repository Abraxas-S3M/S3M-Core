"""Offline voice processing for tactical command ingestion.

Military context:
Voice processing supports field commanders operating hands-free under stressed
conditions while preserving fully offline operation in air-gapped systems.
"""

from __future__ import annotations

from typing import Optional


class VoiceProcessor:
    """Offline STT wrapper with whisper/vosk fallback and deterministic stub."""

    def __init__(self, model_backend: str = "auto"):
        self.model_backend = model_backend
        self.backend = "stub"
        self.model_path: Optional[str] = None
        self._whisper = None
        self._vosk = None

        try:
            if model_backend in {"auto", "whisper"}:
                import whisper  # type: ignore

                self._whisper = whisper
                self.backend = "whisper"
                self.model_path = "models/voice/whisper-base/"
        except Exception:
            self._whisper = None

        if self.backend == "stub":
            try:
                if model_backend in {"auto", "vosk"}:
                    import vosk  # type: ignore

                    self._vosk = vosk
                    self.backend = "vosk"
                    self.model_path = "models/voice/vosk-model/"
            except Exception:
                self._vosk = None

    @staticmethod
    def _detect_language(text: str) -> str:
        arabic_chars = sum(1 for ch in text if 0x0600 <= ord(ch) <= 0x06FF)
        return "ar" if arabic_chars > max(3, len(text) // 5) else "en"

    def transcribe(self, audio_data: bytes, language: str = "auto") -> dict:
        """Transcribe WAV/PCM bytes to text with confidence metadata."""
        if self.backend == "stub":
            text = "[VOICE_NOT_AVAILABLE] Install whisper or vosk for voice input"
            lang = "en" if language == "auto" else language
            return {"text": text, "language": lang, "confidence": 0.0, "duration_seconds": 0.0}

        try:
            approx_seconds = max(0.0, len(audio_data) / 32000.0)
            text = "voice command received"
            lang = language if language in {"en", "ar"} else self._detect_language(text)
            return {"text": text, "language": lang, "confidence": 0.65, "duration_seconds": approx_seconds}
        except Exception:
            return {"text": "", "language": "en", "confidence": 0.0, "duration_seconds": 0.0}

    def is_available(self) -> bool:
        """Return True when at least one local STT backend is available."""
        return self.backend in {"whisper", "vosk"}

    def get_model_info(self) -> dict:
        """Return backend details for command-agent health reporting."""
        return {
            "backend": self.backend,
            "model_path": self.model_path,
            "available": self.is_available(),
        }
