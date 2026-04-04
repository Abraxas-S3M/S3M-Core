"""
S3M Inference Engine
Loads GGUF models via llama-cpp-python and runs local GPU-accelerated inference.
Designed for NVIDIA Jetson AGX Orin 64GB with CUDA.
"""

import time
import logging
from typing import Optional, Dict
from pathlib import Path

try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    LLAMA_CPP_AVAILABLE = False

from .engine_registry import EngineRegistry, EngineID, EngineConfig
from src.edge_runtime.model_manifest import ModelManifest
from src.llm_core.backends import BackendFactory, InferenceBackend

logger = logging.getLogger("s3m.inference")


class InferenceResult:
    def __init__(
        self,
        engine_id: EngineID,
        prompt: str,
        response: str,
        tokens_generated: int,
        prompt_tokens: int,
        latency_ms: float,
        tokens_per_second: float,
        model_name: str,
    ):
        self.engine_id = engine_id
        self.prompt = prompt
        self.response = response
        self.tokens_generated = tokens_generated
        self.prompt_tokens = prompt_tokens
        self.latency_ms = latency_ms
        self.tokens_per_second = tokens_per_second
        self.model_name = model_name

    def to_dict(self) -> Dict:
        return {
            "engine": self.engine_id.value,
            "model": self.model_name,
            "prompt": self.prompt,
            "response": self.response,
            "tokens_generated": self.tokens_generated,
            "prompt_tokens": self.prompt_tokens,
            "latency_ms": round(self.latency_ms, 2),
            "tokens_per_second": round(self.tokens_per_second, 2),
        }


class InferenceEngine:
    """
    Manages a single llama.cpp model instance.
    One InferenceEngine per model. The orchestrator holds four of these.
    """

    def __init__(
        self,
        engine_id: EngineID,
        n_gpu_layers: int = -1,
        n_ctx: Optional[int] = None,
        backend: Optional[InferenceBackend] = None,
    ):
        self.registry = EngineRegistry()
        self.config: EngineConfig = self.registry.get_config(engine_id)
        self.engine_id = engine_id
        self.n_gpu_layers = n_gpu_layers
        self.n_ctx = n_ctx or self.config.context_window
        self.model: Optional[object] = None
        self.backend: Optional[InferenceBackend] = backend
        self.loaded = False

    @staticmethod
    def _resolve_engine_id(model_id: str) -> EngineID:
        try:
            return EngineID(model_id)
        except ValueError:
            registry = EngineRegistry()
            for engine_id, config in registry.configs.items():
                if str(config.name).strip().lower() == str(model_id).strip().lower():
                    return engine_id
            raise ValueError(f"Unknown model_id for engine registry: {model_id}")

    @classmethod
    def from_manifest(
        cls,
        model_id: str,
        variant_tag: str = None,
        manifest_dir: str = "configs/model_manifests",
    ) -> "InferenceEngine":
        """
        Factory method that:
        1. Loads manifest via ModelManifest
        2. Selects best CPU variant if variant_tag is None
        3. Instantiates appropriate backend via BackendFactory
        4. Returns an InferenceEngine wrapping that backend
        """
        manifest = ModelManifest.load(model_id=model_id, manifest_dir=manifest_dir)
        variant = manifest.get_best_cpu_variant(variant_tag=variant_tag)
        backend = cls._create_backend_from_manifest(manifest, variant)
        engine_id = cls._resolve_engine_id(manifest.model_id)
        return cls(engine_id=engine_id, n_gpu_layers=0, n_ctx=variant.max_context, backend=backend)

    @staticmethod
    def _create_backend_from_manifest(manifest: ModelManifest, variant) -> InferenceBackend:
        """Construct backend across both factory API variants."""
        # Newer backend factory signature from main: create(runtime_format, model_path, config)
        if hasattr(variant, "runtime_format") and hasattr(variant, "file_path"):
            runtime_format = str(getattr(variant, "runtime_format", "gguf"))
            model_path = str(getattr(variant, "file_path", ""))
            config = {
                "model_id": manifest.model_id,
                "variant_tag": getattr(variant, "variant_tag", "default"),
                "n_ctx": int(getattr(variant, "max_context", 4096)),
                "runtime_backend": getattr(manifest, "runtime_backend", "llama_cpp"),
            }
            return BackendFactory.create(runtime_format, model_path, config)
        # Legacy local signature from branch: create(model_id, variant)
        return BackendFactory.create(model_id=manifest.model_id, variant=variant)

    def is_available(self) -> bool:
        if self.backend is not None:
            try:
                health = self.backend.health_check()
                return bool(health.get("model_file_exists", False))
            except Exception:
                return False
        if not LLAMA_CPP_AVAILABLE:
            logger.warning("llama-cpp-python is not installed")
            return False
        model_path = Path(self.config.local_path)
        if not model_path.exists():
            logger.warning(f"Model file not found: {model_path}")
            return False
        return True

    def load(self) -> bool:
        if self.backend is not None:
            loaded = bool(self.backend.load())
            self.loaded = loaded
            if loaded:
                self.registry.mark_loaded(self.engine_id)
            return loaded

        if not LLAMA_CPP_AVAILABLE:
            logger.error("Cannot load model: llama-cpp-python not installed")
            return False

        model_path = Path(self.config.local_path)
        if not model_path.exists():
            logger.error(f"Cannot load model: file not found at {model_path}")
            return False

        try:
            logger.info(f"Loading {self.config.name} from {model_path}...")
            start = time.time()

            self.model = Llama(
                model_path=str(model_path),
                n_gpu_layers=self.n_gpu_layers,
                n_ctx=self.n_ctx,
                verbose=False,
            )

            elapsed = (time.time() - start) * 1000
            self.loaded = True
            self.registry.mark_loaded(self.engine_id)
            logger.info(f"{self.config.name} loaded in {elapsed:.0f}ms")
            return True

        except Exception as e:
            logger.error(f"Failed to load {self.config.name}: {e}")
            return False

    def unload(self):
        if self.backend is not None:
            self.backend.unload()
            self.loaded = False
            return
        if self.model is not None:
            del self.model
            self.model = None
            self.loaded = False
            logger.info(f"{self.config.name} unloaded")

    def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        top_p: float = 0.9,
        stop: Optional[list] = None,
        system_prompt: Optional[str] = None,
    ) -> InferenceResult:
        if self.backend is not None:
            if not self.loaded:
                return InferenceResult(
                    engine_id=self.engine_id,
                    prompt=prompt,
                    response="[ERROR] Backend not loaded",
                    tokens_generated=0,
                    prompt_tokens=0,
                    latency_ms=0.0,
                    tokens_per_second=0.0,
                    model_name=self.config.name,
                )
            max_tokens = max_tokens or self.config.max_tokens
            backend_output = self.backend.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=stop,
                system_prompt=system_prompt,
            )
            tps = (
                backend_output.tokens_generated / (backend_output.latency_ms / 1000.0)
                if backend_output.latency_ms > 0
                else 0.0
            )
            return InferenceResult(
                engine_id=self.engine_id,
                prompt=prompt,
                response=backend_output.text,
                tokens_generated=backend_output.tokens_generated,
                prompt_tokens=backend_output.prompt_tokens,
                latency_ms=backend_output.latency_ms,
                tokens_per_second=tps,
                model_name=backend_output.model_name,
            )

        if not self.loaded or self.model is None:
            return InferenceResult(
                engine_id=self.engine_id,
                prompt=prompt,
                response="[ERROR] Model not loaded",
                tokens_generated=0,
                prompt_tokens=0,
                latency_ms=0.0,
                tokens_per_second=0.0,
                model_name=self.config.name,
            )

        max_tokens = max_tokens or self.config.max_tokens

        if system_prompt:
            full_prompt = f"<|system|>\n{system_prompt}\n<|user|>\n{prompt}\n<|assistant|>\n"
        else:
            full_prompt = f"<|user|>\n{prompt}\n<|assistant|>\n"

        try:
            start = time.time()

            output = self.model(
                full_prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=stop or ["<|end|>", "<|user|>"],
                echo=False,
            )

            elapsed_ms = (time.time() - start) * 1000
            response_text = output["choices"][0]["text"].strip()
            tokens_generated = output["usage"]["completion_tokens"]
            prompt_tokens = output["usage"]["prompt_tokens"]
            tps = (tokens_generated / (elapsed_ms / 1000)) if elapsed_ms > 0 else 0

            return InferenceResult(
                engine_id=self.engine_id,
                prompt=prompt,
                response=response_text,
                tokens_generated=tokens_generated,
                prompt_tokens=prompt_tokens,
                latency_ms=elapsed_ms,
                tokens_per_second=tps,
                model_name=self.config.name,
            )

        except Exception as e:
            logger.error(f"Inference failed on {self.config.name}: {e}")
            return InferenceResult(
                engine_id=self.engine_id,
                prompt=prompt,
                response=f"[ERROR] Inference failed: {str(e)}",
                tokens_generated=0,
                prompt_tokens=0,
                latency_ms=0.0,
                tokens_per_second=0.0,
                model_name=self.config.name,
            )

    def health_check(self) -> Dict:
        backend_health: Dict[str, object] = {}
        if self.backend is not None:
            try:
                backend_health = self.backend.health_check()
            except Exception:
                backend_health = {"backend": "unknown", "error": "health_check_failed"}
        return {
            "engine": self.engine_id.value,
            "model": self.config.name,
            "provider": self.config.provider,
            "loaded": self.loaded,
            "model_file_exists": bool(
                backend_health.get("model_file_exists", Path(self.config.local_path).exists())
            ),
            "llama_cpp_available": LLAMA_CPP_AVAILABLE,
            "gpu_layers": self.n_gpu_layers,
            "context_window": self.n_ctx,
            "backend": backend_health.get("backend", "legacy_llama_cpp"),
            "backend_runtime": backend_health.get("runtime_format"),
            "backend_variant": backend_health.get("variant_tag"),
        }
