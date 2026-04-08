"""OPA-backed doctrine evaluator for tactical ROE checks."""

from __future__ import annotations

import json
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from .policy_bias_engine import PolicyBiasEngine


class OPAEvaluator:
    """Evaluate rules-of-engagement doctrine with OPA and safe fallbacks."""

    def __init__(
        self,
        policy_dir: Optional[Path] = None,
        opa_binary: str = "opa",
        opa_data_ref: str = "data.s3m.roe",
        opa_http_url: str = "http://localhost:8181/v1/data/s3m/roe",
        command_runner: Callable[..., Any] = subprocess.run,
        http_post: Callable[..., Any] = requests.post,
        fallback_engine_factory: Callable[[], Any] = PolicyBiasEngine,
    ) -> None:
        self._policy_dir = policy_dir or (
            Path(__file__).resolve().parents[2] / "configs" / "opa_policies"
        )
        self._opa_binary = opa_binary
        self._opa_data_ref = opa_data_ref
        self._opa_http_url = opa_http_url
        self._command_runner = command_runner
        self._http_post = http_post
        self._fallback_engine_factory = fallback_engine_factory
        self._policy_files = self._load_policy_files()

    def _load_policy_files(self) -> List[Path]:
        if not self._policy_dir.exists():
            return []
        return sorted(path for path in self._policy_dir.glob("*.rego") if path.is_file())

    def _normalize_context(self, decision_context: Dict[str, Any]) -> Dict[str, Any]:
        # Tactical context fields are normalized so ROE checks stay deterministic across adapters.
        return {
            "decision_id": str(decision_context.get("decision_id", "unknown")),
            "target_type": str(decision_context.get("target_type", "unknown")),
            "positive_id": bool(decision_context.get("positive_id", False)),
            "near_civilian_zone": bool(decision_context.get("near_civilian_zone", False)),
        }

    def _extract_opa_value(self, payload: Dict[str, Any]) -> Any:
        if "result" not in payload:
            return None
        result_value = payload.get("result")
        if isinstance(result_value, list):
            if not result_value:
                return None
            first = result_value[0] if isinstance(result_value[0], dict) else {}
            expressions = first.get("expressions", []) if isinstance(first, dict) else []
            if not expressions:
                return None
            expression = expressions[0] if isinstance(expressions[0], dict) else {}
            return expression.get("value")
        return result_value

    def _normalize_opa_result(self, value: Any) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        if isinstance(value, bool):
            return {
                "compliant": value,
                "violations": [] if value else ["ROE policy denied decision context."],
                "policy": self._opa_data_ref.replace("data.", ""),
            }
        if not isinstance(value, dict):
            return None
        compliant = bool(value.get("allow", False))
        violations: List[str] = []
        deny_reason = value.get("deny_reason")
        if isinstance(deny_reason, str) and deny_reason.strip() and not compliant:
            violations.append(deny_reason.strip())
        if not compliant and not violations:
            violations.append("ROE policy denied decision context.")
        return {
            "compliant": compliant,
            "violations": violations,
            "policy": self._opa_data_ref.replace("data.", ""),
        }

    def _evaluate_with_local_opa(self, decision_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self._policy_files:
            return None
        input_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", suffix=".json", delete=False
            ) as input_file:
                input_path = input_file.name
                json.dump(decision_context, input_file, ensure_ascii=True)
            command = [
                self._opa_binary,
                "eval",
                "--format=json",
                "--data",
                str(self._policy_dir),
                "--input",
                input_path,
                self._opa_data_ref,
            ]
            completed = self._command_runner(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if getattr(completed, "returncode", 1) != 0:
                return None
            payload = json.loads(getattr(completed, "stdout", "{}") or "{}")
            return self._normalize_opa_result(self._extract_opa_value(payload))
        except (OSError, ValueError, TimeoutError, subprocess.SubprocessError):
            return None
        finally:
            if input_path:
                try:
                    Path(input_path).unlink(missing_ok=True)
                except OSError:
                    pass

    def _evaluate_with_localhost_api(self, decision_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            response = self._http_post(
                self._opa_http_url,
                json={"input": decision_context},
                timeout=1.0,
            )
            if getattr(response, "status_code", 500) != 200:
                return None
            body = response.json() if hasattr(response, "json") else {}
            return self._normalize_opa_result(self._extract_opa_value(body))
        except (requests.RequestException, ValueError, TypeError):
            return None

    def _evaluate_with_policy_bias_engine(
        self, decision_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            engine = self._fallback_engine_factory()
            if hasattr(engine, "check_decision"):
                checks = engine.check_decision(
                    str(decision_context.get("decision_id", "unknown"))
                )
                if isinstance(checks, list) and checks:
                    compliant = all(bool(item.get("compliant", False)) for item in checks)
                    violations = [
                        str(item.get("details", "Doctrine policy violation detected."))
                        for item in checks
                        if not bool(item.get("compliant", False))
                    ]
                    policy_names = ",".join(
                        sorted({str(item.get("policyName", "policy-bias-engine")) for item in checks})
                    )
                    return {
                        "compliant": compliant,
                        "violations": violations,
                        "policy": policy_names or "policy-bias-engine",
                    }
        except Exception:
            pass
        # Fail closed so tactical actions are not marked compliant without any doctrine signal.
        return {
            "compliant": False,
            "violations": ["OPA unavailable and doctrine fallback checks are unavailable."],
            "policy": "policy-bias-engine",
        }

    def evaluate_decision(self, decision_context: Dict[str, Any]) -> Dict[str, Any]:
        """Return normalized doctrine compliance for a tactical decision context."""
        normalized_context = self._normalize_context(decision_context or {})
        local_result = self._evaluate_with_local_opa(normalized_context)
        if local_result is not None:
            return local_result
        localhost_result = self._evaluate_with_localhost_api(normalized_context)
        if localhost_result is not None:
            return localhost_result
        return self._evaluate_with_policy_bias_engine(normalized_context)
