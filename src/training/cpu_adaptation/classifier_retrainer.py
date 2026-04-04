"""CPU-only classifier retraining for tactical edge threat workflows."""

from __future__ import annotations

import io
import logging
import os
import pickle
import resource
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

try:
    import joblib  # type: ignore

    JOBLIB_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    joblib = None  # type: ignore
    JOBLIB_AVAILABLE = False

try:
    import torch  # type: ignore

    TORCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    torch = None  # type: ignore
    TORCH_AVAILABLE = False

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None  # type: ignore

try:
    from sklearn.ensemble import RandomForestClassifier  # type: ignore
    from sklearn.linear_model import LogisticRegression  # type: ignore

    SKLEARN_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    RandomForestClassifier = None  # type: ignore
    LogisticRegression = None  # type: ignore
    SKLEARN_AVAILABLE = False

try:
    from xgboost import XGBClassifier  # type: ignore

    XGBOOST_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    XGBClassifier = None  # type: ignore
    XGBOOST_AVAILABLE = False


logger = logging.getLogger("s3m.training.classifier_retrainer")


@dataclass
class ClassifierConfig:
    """Configuration for CPU-safe classifier updates on edge nodes."""

    n_classes: int
    feature_dim: int
    max_train_time_sec: int = 60
    max_memory_mb: int = 1024


@dataclass
class ClassifierResult:
    """Training outcome summary for tactical model readiness tracking."""

    accuracy: float
    f1_weighted: float
    train_time_sec: float
    model_size_kb: float


class ClassifierRetrainer:
    """Retrains lightweight classifiers using pre-tokenized feature vectors.

    Military/tactical context:
    Retraining runs on pre-extracted numeric features so multilingual theaters
    (Arabic/English and mixed comms) can use the same edge retraining pipeline
    without shipping raw text across disconnected command boundaries.
    """

    SUPPORTED_MODELS = {"random_forest", "xgboost", "mlp_torch", "logistic"}

    def __init__(self, model_type: str, config: ClassifierConfig) -> None:
        if model_type not in self.SUPPORTED_MODELS:
            raise ValueError(f"model_type must be one of {sorted(self.SUPPORTED_MODELS)}")
        if int(config.n_classes) < 2:
            raise ValueError("n_classes must be >= 2")
        if int(config.feature_dim) < 1:
            raise ValueError("feature_dim must be >= 1")
        if int(config.max_train_time_sec) <= 0:
            raise ValueError("max_train_time_sec must be > 0")
        if int(config.max_memory_mb) <= 0:
            raise ValueError("max_memory_mb must be > 0")

        self.model_type = model_type
        self.config = config
        self._model: Any = None
        self._is_torch_model = False
        self._torch_hidden_dim = max(16, min(256, config.feature_dim * 2))
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        if TORCH_AVAILABLE and torch.cuda.is_available():
            logger.info("CUDA detected but disabled; forcing CPU-only retraining")

    @staticmethod
    def _current_rss_mb() -> float:
        if psutil is not None:
            process = psutil.Process(os.getpid())
            return float(process.memory_info().rss) / (1024.0 * 1024.0)
        usage_kb = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return usage_kb / 1024.0

    def _enforce_limits(self, started: float) -> None:
        elapsed = time.perf_counter() - started
        if elapsed > float(self.config.max_train_time_sec):
            raise TimeoutError(
                f"Training exceeded max_train_time_sec={self.config.max_train_time_sec}"
            )
        rss_mb = self._current_rss_mb()
        if rss_mb > float(self.config.max_memory_mb):
            raise MemoryError(
                f"Training exceeded max_memory_mb={self.config.max_memory_mb} (rss={rss_mb:.2f})"
            )

    def _validate_xy(self, X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        if not isinstance(X, np.ndarray) or not isinstance(y, np.ndarray):
            raise ValueError("X and y must be numpy arrays")
        if X.ndim != 2:
            raise ValueError("X must be a 2D array of pre-tokenized numeric features")
        if y.ndim != 1:
            raise ValueError("y must be a 1D array")
        if X.shape[0] != y.shape[0]:
            raise ValueError("X and y must contain the same number of samples")
        if X.shape[1] != int(self.config.feature_dim):
            raise ValueError(
                f"X feature dimension mismatch: expected {self.config.feature_dim}, got {X.shape[1]}"
            )
        if X.shape[0] == 0:
            raise ValueError("X and y cannot be empty")
        y_min = int(np.min(y))
        y_max = int(np.max(y))
        if y_min < 0 or y_max >= int(self.config.n_classes):
            raise ValueError("y labels must be in [0, n_classes)")
        return X.astype(np.float32, copy=False), y.astype(np.int64, copy=False)

    @staticmethod
    def _weighted_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        classes = np.unique(y_true)
        supports = np.array([(y_true == cls).sum() for cls in classes], dtype=np.float64)
        if supports.sum() <= 0:
            return 0.0

        weighted = 0.0
        for cls, support in zip(classes, supports):
            tp = float(np.sum((y_true == cls) & (y_pred == cls)))
            fp = float(np.sum((y_true != cls) & (y_pred == cls)))
            fn = float(np.sum((y_true == cls) & (y_pred != cls)))
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            if precision + recall > 0:
                f1 = (2.0 * precision * recall) / (precision + recall)
            else:
                f1 = 0.0
            weighted += f1 * (support / supports.sum())
        return float(weighted)

    def _build_torch_model(self) -> torch.nn.Module:
        if not TORCH_AVAILABLE or torch is None:
            raise RuntimeError("torch is required for mlp_torch retraining")
        return torch.nn.Sequential(
            torch.nn.Linear(self.config.feature_dim, self._torch_hidden_dim),
            torch.nn.ReLU(),
            torch.nn.Linear(self._torch_hidden_dim, self.config.n_classes),
        )

    def _train_torch_mlp(self, X: np.ndarray, y: np.ndarray, started: float) -> None:
        if not TORCH_AVAILABLE or torch is None:
            raise RuntimeError("torch is required for mlp_torch retraining")
        model = self._build_torch_model().to(torch.device("cpu"))
        optim = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = torch.nn.CrossEntropyLoss()
        batch_size = min(32, max(1, X.shape[0]))
        epochs = 0

        x_tensor = torch.from_numpy(X).to(torch.device("cpu"))
        y_tensor = torch.from_numpy(y).to(torch.device("cpu"))

        model.train()
        while True:
            self._enforce_limits(started)
            order = torch.randperm(x_tensor.shape[0], device=torch.device("cpu"))
            for i in range(0, x_tensor.shape[0], batch_size):
                self._enforce_limits(started)
                idx = order[i : i + batch_size]
                xb = x_tensor[idx]
                yb = y_tensor[idx]
                logits = model(xb)
                loss = criterion(logits, yb)
                optim.zero_grad(set_to_none=True)
                loss.backward()
                optim.step()
            epochs += 1
            if epochs >= 30:
                break

        self._model = model
        self._is_torch_model = True

    def _estimate_model_size_kb(self) -> float:
        if self._model is None:
            return 0.0
        if self._is_torch_model:
            if not TORCH_AVAILABLE or torch is None:
                raise RuntimeError("torch is required for torch model size estimation")
            buffer = io.BytesIO()
            torch.save(self._model.state_dict(), buffer)
            return float(len(buffer.getvalue())) / 1024.0

        with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as handle:
            tmp_path = handle.name
        try:
            if JOBLIB_AVAILABLE and joblib is not None:
                joblib.dump(self._model, tmp_path)
            else:
                with open(tmp_path, "wb") as handle:
                    pickle.dump(self._model, handle)
            return float(os.path.getsize(tmp_path)) / 1024.0
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def train(self, X: np.ndarray, y: np.ndarray) -> ClassifierResult:
        """Train configured classifier on CPU and return quality/footprint metrics."""
        X, y = self._validate_xy(X, y)
        started = time.perf_counter()
        self._enforce_limits(started)

        if self.model_type == "mlp_torch":
            self._train_torch_mlp(X, y, started)
        elif self.model_type == "random_forest":
            if not SKLEARN_AVAILABLE or RandomForestClassifier is None:
                raise RuntimeError("scikit-learn is required for random_forest retraining")
            model = RandomForestClassifier(n_estimators=100, random_state=42, n_jobs=1)
            model.fit(X, y)
            self._model = model
            self._is_torch_model = False
        elif self.model_type == "logistic":
            if not SKLEARN_AVAILABLE or LogisticRegression is None:
                raise RuntimeError("scikit-learn is required for logistic retraining")
            model = LogisticRegression(max_iter=300, n_jobs=1)
            model.fit(X, y)
            self._model = model
            self._is_torch_model = False
        else:  # xgboost
            if XGBOOST_AVAILABLE and XGBClassifier is not None:
                objective = "multi:softmax" if self.config.n_classes > 2 else "binary:logistic"
                model = XGBClassifier(
                    n_estimators=100,
                    max_depth=5,
                    learning_rate=0.1,
                    objective=objective,
                    num_class=self.config.n_classes if self.config.n_classes > 2 else None,
                    tree_method="hist",
                    device="cpu",
                    n_jobs=1,
                    subsample=0.9,
                )
                model.fit(X, y)
                self._model = model
                self._is_torch_model = False
            else:
                logger.warning("xgboost unavailable; falling back to logistic retraining")
                if not SKLEARN_AVAILABLE or LogisticRegression is None:
                    raise RuntimeError("xgboost unavailable and sklearn logistic fallback unavailable")
                model = LogisticRegression(max_iter=300, n_jobs=1)
                model.fit(X, y)
                self._model = model
                self._is_torch_model = False

        self._enforce_limits(started)
        y_pred = self.predict(X)
        accuracy = float(np.mean(y_pred == y))
        f1_weighted = self._weighted_f1(y, y_pred)
        train_time = time.perf_counter() - started
        model_size = self._estimate_model_size_kb()

        return ClassifierResult(
            accuracy=accuracy,
            f1_weighted=f1_weighted,
            train_time_sec=train_time,
            model_size_kb=model_size,
        )

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Run CPU inference for trained classifier on pre-tokenized features."""
        if self._model is None:
            raise RuntimeError("Model has not been trained")
        if not isinstance(X, np.ndarray) or X.ndim != 2:
            raise ValueError("X must be a 2D numpy array")
        if X.shape[1] != int(self.config.feature_dim):
            raise ValueError(
                f"X feature dimension mismatch: expected {self.config.feature_dim}, got {X.shape[1]}"
            )

        Xf = X.astype(np.float32, copy=False)
        if self._is_torch_model:
            if not TORCH_AVAILABLE or torch is None:
                raise RuntimeError("torch is required for mlp_torch prediction")
            self._model.eval()
            with torch.no_grad():
                logits = self._model(torch.from_numpy(Xf).to(torch.device("cpu")))
            return torch.argmax(logits, dim=1).cpu().numpy().astype(np.int64)

        preds = self._model.predict(Xf)
        return np.asarray(preds, dtype=np.int64)

    def export(self, path: str) -> str:
        """Export trained classifier as joblib by default, ONNX for torch MLP."""
        if self._model is None:
            raise RuntimeError("Model has not been trained")
        if not isinstance(path, str) or not path.strip():
            raise ValueError("path must be a non-empty string")

        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        if out_path.suffix.lower() == ".onnx":
            if not self._is_torch_model:
                raise RuntimeError("ONNX export is currently supported only for mlp_torch models")
            if not TORCH_AVAILABLE or torch is None:
                raise RuntimeError("torch is required for ONNX export")
            dummy_input = torch.zeros((1, self.config.feature_dim), dtype=torch.float32)
            self._model.eval()
            torch.onnx.export(
                self._model,
                dummy_input,
                str(out_path),
                input_names=["features"],
                output_names=["logits"],
                dynamic_axes={"features": {0: "batch"}, "logits": {0: "batch"}},
                opset_version=12,
            )
            return str(out_path)

        if self._is_torch_model:
            payload = {
                "model_type": self.model_type,
                "config": asdict(self.config),
                "hidden_dim": self._torch_hidden_dim,
                "state_dict": self._model.state_dict(),
            }
            if JOBLIB_AVAILABLE and joblib is not None:
                joblib.dump(payload, str(out_path))
            else:
                with open(out_path, "wb") as handle:
                    pickle.dump(payload, handle)
            return str(out_path)

        if JOBLIB_AVAILABLE and joblib is not None:
            joblib.dump(self._model, str(out_path))
        else:
            with open(out_path, "wb") as handle:
                pickle.dump(self._model, handle)
        return str(out_path)


class CPUClassifierRetrainer:
    """Compatibility wrapper preserving legacy retrain() interface."""

    def retrain(self, model_type: str, X: Any, y: Any) -> ClassifierResult:
        X_arr = np.asarray(X, dtype=np.float32)
        if X_arr.ndim == 1:
            X_arr = X_arr.reshape(-1, 1)
        y_arr = np.asarray(y, dtype=np.int64)
        if y_arr.ndim != 1:
            y_arr = y_arr.reshape(-1)
        if X_arr.shape[0] <= 0 or y_arr.shape[0] <= 0 or X_arr.shape[0] != y_arr.shape[0]:
            return ClassifierResult(accuracy=0.0, f1_weighted=0.0, train_time_sec=0.0, model_size_kb=0.0)

        classes = int(np.max(y_arr)) + 1
        classes = max(2, classes)
        config = ClassifierConfig(n_classes=classes, feature_dim=int(X_arr.shape[1]))
        retrainer = ClassifierRetrainer(model_type=model_type, config=config)
        return retrainer.train(X_arr, y_arr)
