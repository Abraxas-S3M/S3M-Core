"""Unit tests for environment-driven API configuration."""

from __future__ import annotations

import os
import sys
import tempfile
import types
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

# Offline test environment support: config imports FastAPI and MissionCommandEngine.
if "fastapi" not in sys.modules:
    fastapi_stub = types.ModuleType("fastapi")

    class _FastAPI:  # pragma: no cover - structural import stub
        pass

    fastapi_stub.FastAPI = _FastAPI
    sys.modules["fastapi"] = fastapi_stub

if "src.command.mission_command_engine" not in sys.modules:
    mce_stub = types.ModuleType("src.command.mission_command_engine")

    class _MissionCommandEngine:  # pragma: no cover - structural import stub
        async def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    mce_stub.MissionCommandEngine = _MissionCommandEngine
    sys.modules["src.command.mission_command_engine"] = mce_stub

from src.api import config as config_module


ENV_KEYS = (
    "DEPLOYMENT_MODE",
    "S3M_DEVICE",
    "S3M_HOST",
    "S3M_PORT",
    "S3M_WORKERS",
    "S3M_LOG_LEVEL",
    "S3M_API_KEY",
    "S3M_AUTH_ENABLED",
    "CORS_ORIGINS",
    "S3M_MAX_TOKENS",
    "S3M_TEMPERATURE",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "S3M_MODEL_DIR",
    "S3M_DATA_DIR",
    "S3M_CHECKPOINT_DIR",
    "S3M_DEBUG",
)


@contextmanager
def _isolated_env(overrides: dict[str, str] | None = None):
    env = dict(os.environ)
    for key in ENV_KEYS:
        env.pop(key, None)
    if overrides:
        env.update(overrides)
    with patch.dict(os.environ, env, clear=True):
        yield


@contextmanager
def _temp_cwd():
    prev = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            yield Path(tmp)
        finally:
            os.chdir(prev)


class TestAPIConfig(unittest.TestCase):
    def test_build_config_defaults(self) -> None:
        with _isolated_env(), _temp_cwd(), patch.object(config_module, "_hardware_has_cuda", return_value=False):
            cfg = config_module._build_config()

        self.assertEqual(cfg.deployment_mode, config_module.DeploymentMode.JETSON_EDGE)
        self.assertEqual(cfg.device, "cpu")
        self.assertEqual(cfg.host, "0.0.0.0")
        self.assertEqual(cfg.port, 8080)
        self.assertEqual(cfg.workers, 1)
        self.assertEqual(cfg.log_level, "info")
        self.assertIsNone(cfg.api_key)
        self.assertFalse(cfg.auth_enabled)
        self.assertEqual(cfg.cors_origins, ["*"])
        self.assertEqual(cfg.max_tokens_default, 512)
        self.assertEqual(cfg.temperature_default, 0.7)
        self.assertEqual(cfg.omp_num_threads, 8)
        self.assertEqual(cfg.mkl_num_threads, 8)
        self.assertEqual(cfg.model_dir, "models")
        self.assertEqual(cfg.data_dir, "data")
        self.assertEqual(cfg.checkpoint_dir, "data/checkpoints")
        self.assertEqual(set(cfg.gpu_layers.values()), {0})

    def test_cloud_cpu_demo_forces_cpu_and_hardens_defaults(self) -> None:
        overrides = {"DEPLOYMENT_MODE": "cloud_cpu_demo", "S3M_DEVICE": "cuda"}
        with _isolated_env(overrides), _temp_cwd(), patch.object(config_module, "_hardware_has_cuda", return_value=True):
            cfg = config_module._build_config()

        self.assertEqual(cfg.deployment_mode, config_module.DeploymentMode.CLOUD_CPU_DEMO)
        self.assertEqual(cfg.device, "cpu")
        self.assertTrue(cfg.auth_enabled)
        self.assertEqual(cfg.cors_origins, [])
        self.assertEqual(set(cfg.gpu_layers.values()), {0})

    def test_build_config_accepts_explicit_env_values(self) -> None:
        overrides = {
            "DEPLOYMENT_MODE": "gpu_cluster",
            "S3M_DEVICE": "cuda",
            "S3M_HOST": "127.0.0.1",
            "S3M_PORT": "9090",
            "S3M_WORKERS": "3",
            "S3M_LOG_LEVEL": "debug",
            "S3M_API_KEY": "k1",
            "S3M_AUTH_ENABLED": "true",
            "CORS_ORIGINS": "https://a.example, https://b.example",
            "S3M_MAX_TOKENS": "1024",
            "S3M_TEMPERATURE": "0.25",
            "OMP_NUM_THREADS": "4",
            "MKL_NUM_THREADS": "6",
            "S3M_MODEL_DIR": "m",
            "S3M_DATA_DIR": "d",
            "S3M_CHECKPOINT_DIR": "c",
        }
        with _isolated_env(overrides), _temp_cwd(), patch.object(config_module, "_hardware_has_cuda", return_value=True):
            cfg = config_module._build_config()

        self.assertEqual(cfg.deployment_mode, config_module.DeploymentMode.GPU_CLUSTER)
        self.assertEqual(cfg.device, "cuda")
        self.assertEqual(cfg.host, "127.0.0.1")
        self.assertEqual(cfg.port, 9090)
        self.assertEqual(cfg.workers, 3)
        self.assertEqual(cfg.log_level, "debug")
        self.assertEqual(cfg.api_key, "k1")
        self.assertTrue(cfg.auth_enabled)
        self.assertEqual(cfg.cors_origins, ["https://a.example", "https://b.example"])
        self.assertEqual(cfg.max_tokens_default, 1024)
        self.assertEqual(cfg.temperature_default, 0.25)
        self.assertEqual(cfg.omp_num_threads, 4)
        self.assertEqual(cfg.mkl_num_threads, 6)
        self.assertEqual(cfg.model_dir, "m")
        self.assertEqual(cfg.data_dir, "d")
        self.assertEqual(cfg.checkpoint_dir, "c")

    def test_build_config_loads_dotenv_without_overriding_process_env(self) -> None:
        with _isolated_env(), _temp_cwd() as tmp_dir:
            (tmp_dir / ".env").write_text(
                "S3M_PORT=9001\nCORS_ORIGINS=https://dotenv.example\nS3M_AUTH_ENABLED=true\n",
                encoding="utf-8",
            )
            with patch.object(config_module, "_hardware_has_cuda", return_value=False):
                cfg = config_module._build_config()
                self.assertEqual(cfg.port, 9001)
                self.assertEqual(cfg.cors_origins, ["https://dotenv.example"])
                self.assertTrue(cfg.auth_enabled)

            with _isolated_env({"S3M_PORT": "9010"}), patch.object(config_module, "_hardware_has_cuda", return_value=False):
                cfg_with_override = config_module._build_config()
                self.assertEqual(cfg_with_override.port, 9010)

    def test_get_device_reads_global_api_config(self) -> None:
        with patch.object(config_module, "api_config", config_module.APIConfig(device="cpu")):
            self.assertEqual(config_module.get_device(), "cpu")


if __name__ == "__main__":
    unittest.main(verbosity=2)
