"""
S3M Backend Package
Exposes pluggable air-gapped inference backends for tactical edge deployments.
"""

from .base_backend import InferenceBackend
from .llama_cpp_backend import LlamaCppBackend
from .onnx_backend import OnnxBackend
from .openvino_backend import OpenVinoBackend
from .backend_factory import BackendFactory

__all__ = [
    "InferenceBackend",
    "LlamaCppBackend",
    "OnnxBackend",
    "OpenVinoBackend",
    "BackendFactory",
]
