"""GUI snapshot publisher for CloudFlare Pages fallback data.

Military/tactical context:
Snapshots keep operator workspaces available during contested-network demos
when real-time backend links are interrupted.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from src.storage.object_storage import ObjectStorageConnector

DEFAULT_SNAPSHOT_PREFIX = "gui-snapshots/"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _compute_etag(payload: Dict[str, Any]) -> str:
    return hashlib.md5(_json_bytes(payload)).hexdigest()


def _as_dict(payload: Any) -> Any:
    if hasattr(payload, "model_dump"):
        try:
            return payload.model_dump()
        except Exception:
            return str(payload)
    if isinstance(payload, dict):
        return {str(k): _as_dict(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_as_dict(item) for item in payload]
    if isinstance(payload, tuple):
        return [_as_dict(item) for item in payload]
    if isinstance(payload, (str, int, float, bool)) or payload is None:
        return payload
    return str(payload)


def _workspace_filename(workspace: str) -> str:
    mapping = {
        "system_status": "system-status",
        "training_status": "training-status",
    }
    return mapping.get(workspace, workspace)


def _load_metrics_store_class():
    """Load MetricsStore without relying on package-level import side effects."""
    try:
        from src.training.cloud_cpu.metrics_store import MetricsStore

        return MetricsStore
    except Exception:
        module_path = Path(__file__).resolve().parents[2] / "training" / "cloud_cpu" / "metrics_store.py"
        spec = importlib.util.spec_from_file_location("s3m_metrics_store_runtime", module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load MetricsStore module from {module_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        metrics_store_class = getattr(module, "MetricsStore", None)
        if metrics_store_class is None:
            raise RuntimeError("MetricsStore class is missing from metrics_store module")
        return metrics_store_class


class SnapshotPublisher:
    """Generates and publishes GUI data snapshots to Cloudflare R2.

    Military/tactical context:
    Snapshots provide the CloudFlare Pages frontend with pre-rendered
    data views, enabling demonstration capability even when the live
    backend API is unreachable.
    """

    SUPPORTED_WORKSPACES = (
        "command",
        "cop",
        "decisions",
        "risk",
        "planning",
        "sustainment",
        "readiness",
        "cyber",
        "simulation",
        "communication",
        "surveillance",
        "system_status",
        "training_status",
    )

    def __init__(
        self,
        object_storage_connector: ObjectStorageConnector,
        *,
        metrics_dir: Path | str = "state/training/cloud_cpu/metrics",
        training_state_root: Path | str = "state/training/cloud_cpu",
        snapshot_prefix: str = DEFAULT_SNAPSHOT_PREFIX,
    ) -> None:
        self._object_storage_connector = object_storage_connector
        self._metrics_dir = Path(metrics_dir)
        self._training_state_root = Path(training_state_root)
        metrics_store_class = _load_metrics_store_class()
        self._metrics_store = metrics_store_class(self._metrics_dir)
        self._snapshot_prefix = self._normalize_prefix(snapshot_prefix)

    def generate_all_snapshots(self) -> Dict[str, Any]:
        """Generate snapshot JSON for every GUI workspace.

        Returns dict of workspace_name → snapshot_data.
        Each snapshot matches the API response schema expected by
        the S3M-GUI React components.
        """
        return {
            workspace: self.generate_workspace_snapshot(workspace)
            for workspace in self.SUPPORTED_WORKSPACES
        }

    def generate_workspace_snapshot(self, workspace: str) -> Dict[str, Any]:
        """Generate snapshot for a single workspace.

        Supported workspaces (matching S3M-GUI WORKSPACE_ENDPOINTS):
        - command: operational context + timeline
        - cop: tracks + threat tracks
        - decisions: decision queue
        - risk: risk metrics
        - planning: phases + courses of action
        - sustainment: fleet + supply
        - readiness: readiness summary
        - cyber: incidents + resilience
        - simulation: scenarios
        - communication: messages
        - surveillance: assets
        - system_status: engine health + training status
        - training_status: per-track training metrics from MetricsStore
        """
        normalized = self._validate_workspace(workspace)
        payload_builders = {
            "command": self._build_command_snapshot,
            "cop": self._build_cop_snapshot,
            "decisions": self._build_decisions_snapshot,
            "risk": self._build_risk_snapshot,
            "planning": self._build_planning_snapshot,
            "sustainment": self._build_sustainment_snapshot,
            "readiness": self._build_readiness_snapshot,
            "cyber": self._build_cyber_snapshot,
            "simulation": self._build_simulation_snapshot,
            "communication": self._build_communication_snapshot,
            "surveillance": self._build_surveillance_snapshot,
            "system_status": self._build_system_status_snapshot,
            "training_status": self._build_training_status_payload,
        }
        payload = payload_builders[normalized]()
        return {
            "type": "backend.snapshot",
            "payload": payload,
            "timestamp": _now_iso(),
        }

    def publish_to_object_storage(self, snapshots: Dict[str, Any]) -> Dict[str, Any]:
        """Upload all snapshots to gui-snapshots/ in Cloudflare R2.

        Each workspace gets its own JSON file:
        - gui-snapshots/command.json
        - gui-snapshots/cop.json
        - gui-snapshots/decisions.json
        - gui-snapshots/system-status.json
        - gui-snapshots/training-status.json
        - gui-snapshots/manifest.json (index of all snapshots + timestamps)
        """
        if not isinstance(snapshots, dict):
            raise ValueError("snapshots must be a dictionary")

        manifest_entries: Dict[str, Dict[str, Any]] = {}
        for workspace, snapshot_payload in snapshots.items():
            normalized = self._validate_workspace(workspace)
            safe_payload = _as_dict(snapshot_payload)
            key = f"{self._snapshot_prefix}{_workspace_filename(normalized)}.json"
            result = self._upload_json(key=key, payload=safe_payload)
            manifest_entries[normalized] = self._manifest_entry(
                workspace=normalized,
                key=key,
                payload=safe_payload,
                upload_result=result,
            )

        manifest_payload = {
            "generated_at": _now_iso(),
            "type": "backend.snapshot.manifest",
            "snapshots": manifest_entries,
        }
        manifest_key = f"{self._snapshot_prefix}manifest.json"
        manifest_result = self._upload_json(key=manifest_key, payload=manifest_payload)
        manifest_payload["etag"] = str(manifest_result.get("etag", _compute_etag(manifest_payload)))
        manifest_payload["uploaded_at"] = str(manifest_result.get("uploaded_at", _now_iso()))
        return manifest_payload

    def publish_training_status(self) -> Dict[str, Any]:
        """Specifically publish training metrics — called more frequently.

        Reads from MetricsStore (state/training/cloud_cpu/metrics/)
        and generates training-status.json with:
        - Per-track: current step, loss, samples processed, last eval scores
        - Per-engine: adapter versions, promotion history
        - System: Hetzner health, last sync time, object storage usage
        """
        snapshot = self.generate_workspace_snapshot("training_status")
        self.publish_to_object_storage({"training_status": snapshot})
        return snapshot

    def write_local_snapshots(self, snapshots: Dict[str, Any], output_dir: Path | str) -> Dict[str, Any]:
        """Write snapshots to local files for disconnected validation."""
        output_root = Path(output_dir).resolve()
        output_root.mkdir(parents=True, exist_ok=True)
        manifest_entries: Dict[str, Dict[str, Any]] = {}

        for workspace, payload in snapshots.items():
            normalized = self._validate_workspace(workspace)
            safe_payload = _as_dict(payload)
            filename = f"{_workspace_filename(normalized)}.json"
            destination = (output_root / filename).resolve()
            destination.write_bytes(_json_bytes(safe_payload))
            manifest_entries[normalized] = {
                "workspace": normalized,
                "path": str(destination),
                "etag": _compute_etag(safe_payload),
                "generated_at": str(safe_payload.get("timestamp", _now_iso())),
                "uploaded_at": _now_iso(),
                "size_bytes": destination.stat().st_size,
            }

        manifest_payload = {
            "generated_at": _now_iso(),
            "type": "backend.snapshot.manifest",
            "snapshots": manifest_entries,
        }
        manifest_path = output_root / "manifest.json"
        manifest_path.write_bytes(_json_bytes(manifest_payload))
        return manifest_payload

    def _manifest_entry(
        self,
        *,
        workspace: str,
        key: str,
        payload: Dict[str, Any],
        upload_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        payload_etag = _compute_etag(payload)
        return {
            "workspace": workspace,
            "path": key,
            "etag": str(upload_result.get("etag", payload_etag)),
            "generated_at": str(payload.get("timestamp", _now_iso())),
            "uploaded_at": str(upload_result.get("uploaded_at", _now_iso())),
            "size_bytes": int(upload_result.get("size_bytes", len(_json_bytes(payload)))),
        }

    def _upload_json(self, *, key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if hasattr(self._object_storage_connector, "upload_json"):
            result = self._object_storage_connector.upload_json(key, payload)
            if isinstance(result, dict):
                return result
        encoded = _json_bytes(payload)
        if hasattr(self._object_storage_connector, "upload_bytes"):
            result = self._object_storage_connector.upload_bytes(key, encoded, "application/json")
            if isinstance(result, dict):
                return result
        if hasattr(self._object_storage_connector, "put_object"):
            result = self._object_storage_connector.put_object(key, encoded, "application/json")
            if isinstance(result, dict):
                return result
        raise RuntimeError("Configured object storage connector does not expose a JSON upload method")

    def _build_command_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.agent_adapter import AgentAdapter
        from src.api.gui_bridge.adapters.command_adapter import CommandAdapter

        adapter = CommandAdapter()
        return {
            "operational_context": _as_dict(adapter.get_operational_context()),
            "timeline_events": _as_dict(adapter.get_timeline_events(limit=100)),
            "agents": _as_dict({"agents": [agent.model_dump() for agent in AgentAdapter().get_agents()]}),
            "force_structure": _as_dict(adapter.get_force_structure()),
        }

    def _build_cop_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.cop_adapter import COPAdapter

        adapter = COPAdapter()
        return {
            "tracks": _as_dict(adapter.get_tracks()),
            "threat_tracks": _as_dict(adapter.get_threat_tracks()),
        }

    def _build_decisions_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.decision_adapter import DecisionAdapter

        return {
            "queue": _as_dict(DecisionAdapter().get_queue()),
        }

    def _build_risk_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.risk_adapter import RiskAdapter

        return {
            "metrics": _as_dict(RiskAdapter().get_metrics()),
        }

    def _build_planning_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.planning_adapter import PlanningAdapter

        adapter = PlanningAdapter()
        return {
            "phases": _as_dict(adapter.get_phases()),
            "coas": _as_dict(adapter.get_coas()),
        }

    def _build_sustainment_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.sustainment_adapter import SustainmentAdapter

        adapter = SustainmentAdapter()
        return {
            "fleet": _as_dict(adapter.get_fleet()),
            "supply": _as_dict(adapter.get_supply()),
        }

    def _build_readiness_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.readiness_adapter import ReadinessAdapter

        return {
            "summary": _as_dict(ReadinessAdapter().get_summary()),
        }

    def _build_cyber_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.cyber_adapter import CyberAdapter

        adapter = CyberAdapter()
        return {
            "incidents": _as_dict(adapter.get_incidents()),
            "resilience": _as_dict(adapter.get_resilience()),
        }

    def _build_simulation_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.simulation_adapter import SimulationAdapter

        return {
            "scenarios": _as_dict(SimulationAdapter().get_scenarios()),
        }

    def _build_communication_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.comms_adapter import CommsAdapter

        return {
            "messages": _as_dict(CommsAdapter().get_messages()),
        }

    def _build_surveillance_snapshot(self) -> Dict[str, Any]:
        from src.api.gui_bridge.adapters.surveillance_adapter import SurveillanceAdapter

        return {
            "assets": _as_dict(SurveillanceAdapter().get_assets()),
        }

    def _build_system_status_snapshot(self) -> Dict[str, Any]:
        return {
            "engine_health": {
                "status": "operational",
                "engines": self._collect_engine_status_safe(),
                "uptime": self._collect_uptime_seconds_safe(),
                "updatedAt": _now_iso(),
            },
            "training_status": self._build_training_status_payload(),
        }

    def _build_training_status_payload(self) -> Dict[str, Any]:
        tracks = self._collect_training_tracks()
        return {
            "generated_at": _now_iso(),
            "tracks": tracks,
            "gpu_sessions": self._collect_gpu_sessions(),
            "grok_verdicts": self._collect_grok_verdicts(),
            "engines": self._collect_engine_training_status(tracks),
            "system": self._collect_training_system_status(),
        }

    def _collect_training_tracks(self) -> Dict[str, Dict[str, Any]]:
        track_names = {"saudi_mod", "ukraine_mod", "nato"}
        if self._metrics_dir.exists():
            for metric_file in self._metrics_dir.glob("*.jsonl"):
                track_names.add(metric_file.stem)

        output: Dict[str, Dict[str, Any]] = {}
        for track in sorted(track_names):
            latest = self._metrics_store.get_latest(track, n=250)
            summary = self._metrics_store.get_track_summary(track)
            last = latest[-1] if latest else {}
            output[track] = {
                "current_step": self._resolve_current_step(last=last, summary=summary),
                "last_loss": self._safe_float(last.get("loss")),
                "samples_processed": self._resolve_samples_processed(track=track, rows=latest, summary=summary),
                "last_eval": self._resolve_last_eval(latest),
                "last_promotion": self._resolve_last_promotion(track),
                "active_adapters": self._resolve_active_adapters(track=track, rows=latest),
            }
        return output

    def _collect_gpu_sessions(self) -> Dict[str, Any]:
        sessions: list[dict] = []
        for track in self._collect_track_names():
            rows = self._metrics_store.get_latest(track, n=500)
            for row in rows:
                if isinstance(row.get("gpu_session"), dict):
                    session = dict(row["gpu_session"])
                    if "timestamp" not in session and isinstance(row.get("timestamp"), str):
                        session["timestamp"] = row["timestamp"]
                    sessions.append(session)

        session_file = self._metrics_dir / "gpu_sessions.json"
        if session_file.exists():
            try:
                payload = json.loads(session_file.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("sessions"), list):
                    sessions.extend([s for s in payload["sessions"] if isinstance(s, dict)])
            except Exception:
                pass

        sessions = sorted(sessions, key=lambda s: str(s.get("timestamp", "")))
        last_session = sessions[-1] if sessions else {"engine": None, "duration": "0h 0m", "loss": None}
        today_key = datetime.now(timezone.utc).date().isoformat()
        sessions_today = sum(1 for session in sessions if str(session.get("timestamp", "")).startswith(today_key))
        total_gpu_hours = round(sum(self._duration_to_hours(str(s.get("duration", "0h 0m"))) for s in sessions), 2)
        return {
            "last_session": {
                "engine": last_session.get("engine"),
                "duration": str(last_session.get("duration", "0h 0m")),
                "loss": self._safe_float(last_session.get("loss")),
            },
            "sessions_today": sessions_today,
            "total_gpu_hours": total_gpu_hours,
        }

    def _collect_grok_verdicts(self) -> Dict[str, Any]:
        verdict_rows: list[dict] = []
        for track in self._collect_track_names():
            for row in self._metrics_store.get_latest(track, n=500):
                verdict = row.get("grok_verdict")
                if isinstance(verdict, dict):
                    payload = dict(verdict)
                    if "timestamp" not in payload and isinstance(row.get("timestamp"), str):
                        payload["timestamp"] = row["timestamp"]
                    verdict_rows.append(payload)

        verdict_file = self._metrics_dir / "grok_verdicts.json"
        if verdict_file.exists():
            try:
                payload = json.loads(verdict_file.read_text(encoding="utf-8"))
                if isinstance(payload, dict) and isinstance(payload.get("verdicts"), list):
                    verdict_rows.extend([row for row in payload["verdicts"] if isinstance(row, dict)])
            except Exception:
                pass

        today_key = datetime.now(timezone.utc).date().isoformat()
        pending = 0
        approved_today = 0
        rejected_today = 0
        for row in verdict_rows:
            status = str(row.get("status", "pending")).strip().lower()
            timestamp = str(row.get("timestamp", ""))
            if status == "pending":
                pending += 1
            if timestamp.startswith(today_key):
                if status in {"approved", "accept"}:
                    approved_today += 1
                if status in {"rejected", "deny"}:
                    rejected_today += 1

        decisions = approved_today + rejected_today
        approval_rate = round((approved_today / decisions), 3) if decisions else 0.0
        return {
            "pending": pending,
            "approved_today": approved_today,
            "rejected_today": rejected_today,
            "approval_rate": approval_rate,
        }

    def _collect_engine_training_status(self, tracks: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        engines: Dict[str, Dict[str, Any]] = {}
        for track_name, track_payload in tracks.items():
            adapters = track_payload.get("active_adapters", {})
            if not isinstance(adapters, dict):
                continue
            promotion = track_payload.get("last_promotion")
            for engine_name, adapter_version in adapters.items():
                bucket = engines.setdefault(
                    str(engine_name),
                    {
                        "active_adapter_versions": [],
                        "tracks": [],
                        "promotion_history": [],
                    },
                )
                if adapter_version not in bucket["active_adapter_versions"]:
                    bucket["active_adapter_versions"].append(adapter_version)
                if track_name not in bucket["tracks"]:
                    bucket["tracks"].append(track_name)
                if promotion is not None:
                    bucket["promotion_history"].append(
                        {
                            "track": track_name,
                            "step": promotion.get("step"),
                            "timestamp": promotion.get("timestamp"),
                        }
                    )
        return engines

    def _collect_training_system_status(self) -> Dict[str, Any]:
        mirror_root = Path("state/gui_bridge/object_storage_mirror")
        object_count = 0
        total_bytes = 0
        if mirror_root.exists():
            for entry in mirror_root.rglob("*"):
                if entry.is_file():
                    object_count += 1
                    total_bytes += entry.stat().st_size

        return {
            "hetzner_health": "degraded" if not self._collect_engine_status_safe() else "operational",
            "last_sync_time": _now_iso(),
            "object_storage_usage": {
                "objects": object_count,
                "bytes": total_bytes,
            },
        }


    @staticmethod
    def _collect_engine_status_safe() -> Dict[str, Any]:
        try:
            from src.api.gui_bridge.system_routes import _collect_engine_status

            payload = _collect_engine_status()
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _collect_uptime_seconds_safe() -> int:
        try:
            from src.api.gui_bridge.system_routes import _collect_uptime_seconds

            value = _collect_uptime_seconds()
            return int(value)
        except Exception:
            return 0

    def _resolve_current_step(self, *, last: Dict[str, Any], summary: Dict[str, Any]) -> int:
        for key in ("step", "current_step", "cycle"):
            value = last.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, float):
                return int(value)
        summary_cycle = summary.get("last_cycle")
        if isinstance(summary_cycle, int):
            return summary_cycle
        if isinstance(summary_cycle, float):
            return int(summary_cycle)
        return 0

    def _resolve_samples_processed(self, *, track: str, rows: list[Dict[str, Any]], summary: Dict[str, Any]) -> int:
        for row in reversed(rows):
            for key in ("samples_processed", "samples", "total_samples"):
                value = row.get(key)
                if isinstance(value, int):
                    return value
                if isinstance(value, float):
                    return int(value)
        sample_count = summary.get("samples")
        if isinstance(sample_count, int):
            return sample_count
        if isinstance(sample_count, float):
            return int(sample_count)
        return len(rows) if track else 0

    def _resolve_last_eval(self, rows: list[Dict[str, Any]]) -> Dict[str, Any]:
        for row in reversed(rows):
            for key in ("last_eval", "eval", "evaluation"):
                value = row.get(key)
                if isinstance(value, dict):
                    return {str(k): self._safe_float(v) for k, v in value.items() if self._safe_float(v) is not None}
            scalar_eval = {}
            for key in ("arabic_fidelity", "overall", "accuracy"):
                value = self._safe_float(row.get(key))
                if value is not None:
                    scalar_eval[key] = value
            if scalar_eval:
                return scalar_eval
        return {}

    def _resolve_last_promotion(self, track: str) -> Dict[str, Any] | None:
        promoted_root = self._training_state_root / "tracks" / track / "checkpoints" / "promoted"
        if not promoted_root.exists():
            return None
        candidates = [path for path in promoted_root.iterdir() if path.is_dir()]
        if not candidates:
            return None
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        manifest_path = latest / "manifest.json"
        if manifest_path.exists():
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    step = payload.get("step")
                    if not isinstance(step, int):
                        step = self._safe_int(step) or 0
                    timestamp = str(payload.get("timestamp", datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat()))
                    return {"step": step, "timestamp": timestamp}
            except Exception:
                pass
        return {
            "step": 0,
            "timestamp": datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat(),
        }

    def _resolve_active_adapters(self, *, track: str, rows: list[Dict[str, Any]]) -> Dict[str, str]:
        for row in reversed(rows):
            for key in ("active_adapters", "adapters"):
                value = row.get(key)
                if isinstance(value, dict):
                    return {str(k): str(v) for k, v in value.items()}

        promoted_root = self._training_state_root / "tracks" / track / "checkpoints" / "promoted"
        if promoted_root.exists():
            candidates = [path for path in promoted_root.iterdir() if path.is_dir()]
            if candidates:
                latest = max(candidates, key=lambda p: p.stat().st_mtime)
                manifest_path = latest / "manifest.json"
                if manifest_path.exists():
                    try:
                        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                        for key in ("active_adapters", "adapters"):
                            value = payload.get(key)
                            if isinstance(value, dict):
                                return {str(k): str(v) for k, v in value.items()}
                    except Exception:
                        pass
        return {}

    def _collect_track_names(self) -> list[str]:
        names: set[str] = set()
        if self._metrics_dir.exists():
            for path in self._metrics_dir.glob("*.jsonl"):
                names.add(path.stem)
        return sorted(names or {"saudi_mod", "ukraine_mod", "nato"})

    @staticmethod
    def _duration_to_hours(duration_text: str) -> float:
        text = str(duration_text).strip().lower()
        if not text:
            return 0.0
        hours = 0.0
        minutes = 0.0
        if "h" in text:
            h_part = text.split("h", 1)[0].strip()
            try:
                hours = float(h_part)
            except ValueError:
                hours = 0.0
            text = text.split("h", 1)[1].strip()
        if "m" in text:
            m_part = text.split("m", 1)[0].strip()
            try:
                minutes = float(m_part)
            except ValueError:
                minutes = 0.0
        return hours + (minutes / 60.0)

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _validate_workspace(self, workspace: str) -> str:
        normalized = str(workspace or "").strip().lower()
        if normalized not in self.SUPPORTED_WORKSPACES:
            raise ValueError(
                f"Unsupported workspace '{workspace}'. "
                f"Supported: {sorted(self.SUPPORTED_WORKSPACES)}"
            )
        return normalized

    @staticmethod
    def _normalize_prefix(prefix: str) -> str:
        normalized = str(prefix or DEFAULT_SNAPSHOT_PREFIX).strip()
        if not normalized:
            normalized = DEFAULT_SNAPSHOT_PREFIX
        if not normalized.endswith("/"):
            normalized += "/"
        return normalized
