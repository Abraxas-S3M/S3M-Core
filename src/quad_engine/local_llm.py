"""Safe, opt-in local LLM runner for the Quad-Engine Orchestration Layer.

Tactical context:
    This module is a *guarded* wrapper around a local llama.cpp binary for
    on-device (air-gapped Jetson AGX Orin) inference. It exists so the demo can
    upgrade individual engines from deterministic placeholders to live local
    reasoning when a quantized GGUF model is present.

Hard safety rules enforced here:
    * Disabled unless ``S3M_ENABLE_LOCAL_LLM=true``. Default is OFF.
    * No external API calls. Only a local subprocess is ever spawned.
    * No shell: the subprocess is launched with an argument list and
      ``shell=False`` so prompts can never inject shell commands.
    * No arbitrary model paths: the model file is resolved exclusively from the
      trusted model registry (bare filename under ``S3M_MODELS_DIR``); caller
      input cannot choose the model path.
    * Bounded by a hard timeout; on any failure it returns ``None`` so callers
      fall back to deterministic placeholder output (the demo never errors out).
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Optional

from src.quad_engine.model_registry import ModelRegistry, get_registry, local_llm_enabled

LOGGER = logging.getLogger(__name__)

# Hard ceiling on local inference wall-clock time (seconds). Keeps a wedged
# subprocess from blocking the API request path.
_DEFAULT_TIMEOUT_SECONDS = 45.0


def _llamacpp_bin() -> str:
    return os.environ.get("S3M_LLAMACPP_BIN", "/opt/s3m/bin/llama-cli")


class LocalLLMRunner:
    """Guarded llama.cpp subprocess runner.

    The runner is intentionally minimal. It is *available* only when all of the
    following hold: the enable flag is set, the binary exists and is
    executable, and the requested engine has an approved model file present.
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        *,
        binary_path: Optional[str] = None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._registry = registry or get_registry()
        self._binary_path = binary_path or _llamacpp_bin()
        self._timeout_seconds = max(1.0, float(timeout_seconds))

    @property
    def enabled(self) -> bool:
        return local_llm_enabled()

    def _binary_available(self) -> bool:
        path = self._binary_path
        return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)

    def runner_available(self) -> bool:
        """True only when local inference could actually be performed."""
        return self.enabled and self._binary_available()

    def engine_available(self, engine_id: str) -> bool:
        """True when this specific engine can run live locally."""
        return self.runner_available() and self._registry.model_present(engine_id)

    def generate(
        self,
        engine_id: str,
        prompt: str,
        *,
        system_prompt: str = "",
        max_tokens: Optional[int] = None,
    ) -> Optional[str]:
        """Run local inference for an engine, or return ``None`` to fall back.

        Returning ``None`` (never raising) is deliberate: callers treat ``None``
        as "use the deterministic placeholder", which keeps the demo resilient.
        """
        if not self.runner_available():
            return None

        model_path = self._registry.resolve_model_path(engine_id)
        if not model_path:
            # Engine has no approved/present model -> caller uses placeholder.
            return None

        entry = self._registry.get(engine_id)
        token_budget = int(max_tokens or (entry.max_tokens if entry else 512))
        token_budget = max(1, min(token_budget, 4096))

        # Compose a single prompt. We pass everything as discrete argv entries
        # (shell=False) so no part of the prompt can be interpreted by a shell.
        composed_prompt = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"

        cmd = [
            self._binary_path,
            "-m",
            model_path,
            "-n",
            str(token_budget),
            "-p",
            composed_prompt,
            "--no-display-prompt",
        ]

        try:
            completed = subprocess.run(
                cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
                # Air-gapped runner: scrub the environment to a minimal set.
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            LOGGER.warning("Local LLM run failed for %s: %s", engine_id, exc)
            return None

        if completed.returncode != 0:
            LOGGER.warning(
                "Local LLM exited %s for %s: %s",
                completed.returncode,
                engine_id,
                (completed.stderr or "").strip()[:200],
            )
            return None

        output = (completed.stdout or "").strip()
        return output or None


_GLOBAL_RUNNER: Optional[LocalLLMRunner] = None


def get_local_llm() -> LocalLLMRunner:
    """Return the process-wide local LLM runner singleton."""
    global _GLOBAL_RUNNER
    if _GLOBAL_RUNNER is None:
        _GLOBAL_RUNNER = LocalLLMRunner()
    return _GLOBAL_RUNNER
