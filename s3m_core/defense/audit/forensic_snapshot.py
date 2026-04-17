"""Forensic snapshot capture and post-incident analysis for S3M.

Military/tactical context:
When hostile behavior is detected, commanders need a full, immutable state
capture to reconstruct kill-chain timelines and contain compromise spread.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import resource
import subprocess
import tarfile
import tempfile
from typing import Any, Callable, Dict, List, Mapping, Sequence


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)


@dataclass(slots=True, frozen=True)
class TimelineEvent:
    """One timestamped activity in the forensic timeline."""

    timestamp: datetime
    event: str
    source: str
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": _ensure_utc(self.timestamp).isoformat(),
            "event": self.event,
            "source": self.source,
            "details": dict(self.details),
        }


@dataclass(slots=True, frozen=True)
class ForensicReport:
    """Structured post-incident findings for SOC review."""

    incident_summary: str
    attack_vector_identified: str
    data_compromised: List[str]
    timeline: List[TimelineEvent]
    root_cause: str
    recommendations: List[str]
    confidence: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_summary": self.incident_summary,
            "attack_vector_identified": self.attack_vector_identified,
            "data_compromised": list(self.data_compromised),
            "timeline": [event.to_dict() for event in self.timeline],
            "root_cause": self.root_cause,
            "recommendations": list(self.recommendations),
            "confidence": float(self.confidence),
        }


SnapshotPath = str


class ForensicSnapshot:
    """Capture and analyze complete runtime evidence bundles."""

    def __init__(
        self,
        snapshot_dir: str = "forensic_snapshots",
        *,
        signing_key: bytes | None = None,
        execution_history_provider: Callable[[str], Sequence[Mapping[str, Any]]] | None = None,
        egress_traffic_provider: Callable[[str], Sequence[Mapping[str, Any]]] | None = None,
        audit_entries_provider: Callable[[str], Sequence[Mapping[str, Any]]] | None = None,
        sae_timeline_provider: Callable[[str], Sequence[Mapping[str, Any]]] | None = None,
        emotion_timeline_provider: Callable[[str], Sequence[Mapping[str, Any]]] | None = None,
        verbalizer_provider: Callable[[str], Sequence[Mapping[str, Any]]] | None = None,
        thinking_text_provider: Callable[[str], Sequence[str] | str | None] | None = None,
        llm_analyzer: Callable[[Dict[str, Any]], ForensicReport | Mapping[str, Any]] | None = None,
    ) -> None:
        if not str(snapshot_dir).strip():
            raise ValueError("snapshot_dir must be non-empty")
        self.snapshot_root = Path(snapshot_dir)
        self.snapshot_root.mkdir(parents=True, exist_ok=True)
        self.signing_key = signing_key
        self.execution_history_provider = execution_history_provider
        self.egress_traffic_provider = egress_traffic_provider
        self.audit_entries_provider = audit_entries_provider
        self.sae_timeline_provider = sae_timeline_provider
        self.emotion_timeline_provider = emotion_timeline_provider
        self.verbalizer_provider = verbalizer_provider
        self.thinking_text_provider = thinking_text_provider
        self.llm_analyzer = llm_analyzer

    def capture(self, session_id: str, container_id: str, trigger: str) -> SnapshotPath:
        """Capture a full evidence bundle and return archive path."""
        safe_session = str(session_id).strip()
        safe_container = str(container_id).strip()
        safe_trigger = str(trigger).strip()
        if not safe_session:
            raise ValueError("session_id must be non-empty")
        if not safe_container:
            raise ValueError("container_id must be non-empty")
        if not safe_trigger:
            raise ValueError("trigger must be non-empty")

        timestamp = _utc_now()
        label = timestamp.strftime("%Y%m%dT%H%M%SZ")
        stem = f"{label}_{self._safe_slug(safe_session)}_{self._safe_slug(safe_container)}"
        working_dir = self.snapshot_root / stem
        working_dir.mkdir(parents=True, exist_ok=False)

        metadata = {
            "captured_at": timestamp.isoformat(),
            "session_id": safe_session,
            "container_id": safe_container,
            "trigger": safe_trigger,
        }
        self._write_json(working_dir / "metadata.json", metadata)

        filesystem_capture = self._capture_filesystem_overlay(working_dir)
        process_info = {
            "process_listing": self._capture_command(
                [["ps", "-eo", "pid,ppid,user,%cpu,%mem,start,time,args"]]
            ),
            "process_tree": self._capture_command([["ps", "-ejH"]]),
        }
        network_info = {
            "connections": self._capture_command(
                [["ss", "-tunap"], ["netstat", "-tunap"], ["netstat", "-an"]]
            )
        }
        environment_info = {"variables": self._scrub_environment(os.environ)}
        execution_history = self._coerce_sequence(self._call_provider(self.execution_history_provider, safe_session))
        egress_traffic = self._coerce_sequence(self._call_provider(self.egress_traffic_provider, safe_session))
        audit_entries = self._coerce_sequence(self._call_provider(self.audit_entries_provider, safe_session))
        sae_timeline = self._coerce_sequence(self._call_provider(self.sae_timeline_provider, safe_session))
        emotion_timeline = self._coerce_sequence(self._call_provider(self.emotion_timeline_provider, safe_session))
        verbalizer_descriptions = self._coerce_sequence(
            self._call_provider(self.verbalizer_provider, safe_session)
        )
        extended_thinking = self._coerce_thinking_text(
            self._call_provider(self.thinking_text_provider, safe_session)
        )
        resources = self._capture_resources()

        self._write_json(working_dir / "filesystem_capture.json", filesystem_capture)
        self._write_json(working_dir / "processes.json", process_info)
        self._write_json(working_dir / "network.json", network_info)
        self._write_json(working_dir / "environment.json", environment_info)
        self._write_json(working_dir / "execution_gate_history.json", execution_history)
        self._write_json(working_dir / "egress_proxy_traffic.json", egress_traffic)
        self._write_json(working_dir / "audit_entries.json", audit_entries)
        self._write_json(working_dir / "sae_timeline.json", sae_timeline)
        self._write_json(working_dir / "emotion_timeline.json", emotion_timeline)
        self._write_json(working_dir / "activation_verbalizer_descriptions.json", verbalizer_descriptions)
        self._write_json(working_dir / "resources.json", resources)
        (working_dir / "extended_thinking.txt").write_text(extended_thinking, encoding="utf-8")

        manifest = {
            "metadata": metadata,
            "captured_files": sorted(item.name for item in working_dir.iterdir()),
            "resource_summary": resources,
        }
        self._write_json(working_dir / "snapshot_manifest.json", manifest)

        archive_path = self.snapshot_root / f"{stem}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(working_dir, arcname=working_dir.name)

        archive_hash = self._sha256_file(archive_path)
        Path(f"{archive_path}.sha256").write_text(f"{archive_hash}  {archive_path.name}\n", encoding="utf-8")

        if self.signing_key:
            signature = hmac.new(self.signing_key, archive_hash.encode("utf-8"), hashlib.sha256).hexdigest()
            Path(f"{archive_path}.sig").write_text(signature + "\n", encoding="utf-8")

        return str(archive_path)

    def analyze(self, snapshot_path: str) -> ForensicReport:
        """Analyze captured evidence with isolated logic or supplied offline LLM."""
        archive_path = Path(snapshot_path)
        if not archive_path.exists():
            raise FileNotFoundError(f"Snapshot archive not found: {snapshot_path}")

        snapshot_payload = self._read_archive_payload(archive_path)

        if self.llm_analyzer is not None:
            analysis = self.llm_analyzer(snapshot_payload)
            if isinstance(analysis, ForensicReport):
                return analysis
            if isinstance(analysis, Mapping):
                return self._coerce_report_from_mapping(analysis)
            raise TypeError("llm_analyzer must return ForensicReport or mapping")

        return self._heuristic_analysis(snapshot_payload)

    def _capture_filesystem_overlay(self, output_dir: Path) -> Dict[str, Any]:
        upperdir = self._resolve_overlay_upperdir()
        if upperdir is not None and upperdir.exists():
            overlay_archive = output_dir / "filesystem_overlay.tar.gz"
            try:
                with tarfile.open(overlay_archive, "w:gz") as archive:
                    archive.add(upperdir, arcname="overlay_upperdir")
                return {
                    "mode": "overlay_upperdir_archive",
                    "upperdir": str(upperdir),
                    "artifact": overlay_archive.name,
                }
            except (OSError, tarfile.TarError):
                pass

        # Tactical fallback: capture a local file manifest when overlay diff is unavailable.
        manifest_entries: List[Dict[str, Any]] = []
        workspace_root = Path.cwd()
        max_files = 3000
        for file_path in workspace_root.rglob("*"):
            if len(manifest_entries) >= max_files:
                break
            if not file_path.is_file():
                continue
            stat = file_path.stat()
            manifest_entries.append(
                {
                    "path": str(file_path.relative_to(workspace_root)),
                    "size": int(stat.st_size),
                    "mtime": float(stat.st_mtime),
                }
            )
        manifest_file = output_dir / "filesystem_manifest.json"
        self._write_json(manifest_file, manifest_entries)
        return {
            "mode": "workspace_manifest",
            "artifact": manifest_file.name,
            "captured_files": len(manifest_entries),
            "workspace_root": str(workspace_root),
        }

    @staticmethod
    def _resolve_overlay_upperdir() -> Path | None:
        mountinfo = Path("/proc/self/mountinfo")
        if not mountinfo.exists():
            return None
        try:
            content = mountinfo.read_text(encoding="utf-8")
        except OSError:
            return None
        for line in content.splitlines():
            marker = "upperdir="
            if marker not in line:
                continue
            tail = line.split(marker, maxsplit=1)[1]
            upper = tail.split(",", maxsplit=1)[0].strip()
            if upper:
                return Path(upper)
        return None

    @staticmethod
    def _capture_command(command_candidates: List[List[str]]) -> str:
        for command in command_candidates:
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            output = (result.stdout or "").strip()
            error = (result.stderr or "").strip()
            if output:
                return output
            if error:
                return error
        return "unavailable"

    @staticmethod
    def _scrub_environment(env: Mapping[str, str]) -> Dict[str, str]:
        scrubbed: Dict[str, str] = {}
        sensitive_markers = ("TOKEN", "SECRET", "PASSWORD", "KEY", "CREDENTIAL", "AUTH")
        for key, value in sorted(env.items()):
            normalized_key = key.upper()
            if any(marker in normalized_key for marker in sensitive_markers):
                scrubbed[key] = "[REDACTED]"
                continue
            text = str(value)
            if len(text) > 512:
                text = text[:509] + "..."
            scrubbed[key] = text
        return scrubbed

    @staticmethod
    def _capture_resources() -> Dict[str, Any]:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        meminfo = ""
        meminfo_path = Path("/proc/meminfo")
        if meminfo_path.exists():
            try:
                meminfo = "\n".join(meminfo_path.read_text(encoding="utf-8").splitlines()[:20])
            except OSError:
                meminfo = "unavailable"
        loadavg = ""
        loadavg_path = Path("/proc/loadavg")
        if loadavg_path.exists():
            try:
                loadavg = loadavg_path.read_text(encoding="utf-8").strip()
            except OSError:
                loadavg = "unavailable"
        return {
            "max_rss_kb": int(getattr(usage, "ru_maxrss", 0)),
            "user_cpu_seconds": float(getattr(usage, "ru_utime", 0.0)),
            "system_cpu_seconds": float(getattr(usage, "ru_stime", 0.0)),
            "major_page_faults": int(getattr(usage, "ru_majflt", 0)),
            "minor_page_faults": int(getattr(usage, "ru_minflt", 0)),
            "meminfo_excerpt": meminfo,
            "load_average": loadavg,
        }

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _call_provider(
        provider: Callable[[str], Any] | None,
        session_id: str,
    ) -> Any:
        if provider is None:
            return []
        return provider(session_id)

    @staticmethod
    def _coerce_sequence(payload: Any) -> List[Dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, Mapping):
            return [dict(payload)]
        if isinstance(payload, list):
            normalized: List[Dict[str, Any]] = []
            for item in payload:
                if isinstance(item, Mapping):
                    normalized.append(dict(item))
                else:
                    normalized.append({"value": str(item)})
            return normalized
        if isinstance(payload, tuple):
            return ForensicSnapshot._coerce_sequence(list(payload))
        return [{"value": str(payload)}]

    @staticmethod
    def _coerce_thinking_text(payload: Any) -> str:
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload
        if isinstance(payload, Sequence):
            return "\n".join(str(item) for item in payload)
        return str(payload)

    @staticmethod
    def _safe_slug(value: str) -> str:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
        cleaned = "".join(char if char in allowed else "-" for char in value)
        cleaned = cleaned.strip("-")
        return cleaned or "unknown"

    def _read_archive_payload(self, archive_path: Path) -> Dict[str, Any]:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            with tarfile.open(archive_path, "r:gz") as archive:
                self._safe_extract_tar(archive, temp_path)
            manifest_candidates = list(temp_path.rglob("snapshot_manifest.json"))
            if not manifest_candidates:
                raise ValueError("snapshot_manifest.json missing from archive")
            root = manifest_candidates[0].parent
            payload: Dict[str, Any] = {
                "manifest": json.loads(manifest_candidates[0].read_text(encoding="utf-8")),
                "metadata": self._read_json_if_exists(root / "metadata.json"),
                "audit_entries": self._read_json_if_exists(root / "audit_entries.json"),
                "execution_history": self._read_json_if_exists(root / "execution_gate_history.json"),
                "egress_traffic": self._read_json_if_exists(root / "egress_proxy_traffic.json"),
                "sae_timeline": self._read_json_if_exists(root / "sae_timeline.json"),
                "emotion_timeline": self._read_json_if_exists(root / "emotion_timeline.json"),
                "verbalizer_descriptions": self._read_json_if_exists(
                    root / "activation_verbalizer_descriptions.json"
                ),
                "resources": self._read_json_if_exists(root / "resources.json"),
                "extended_thinking_text": self._read_text_if_exists(root / "extended_thinking.txt"),
            }
            return payload

    @staticmethod
    def _safe_extract_tar(archive: tarfile.TarFile, destination: Path) -> None:
        """Safely extract tar members while blocking path traversal writes."""
        destination_resolved = destination.resolve()
        members = archive.getmembers()
        for member in members:
            member_path = (destination / member.name).resolve()
            common_root = os.path.commonpath([str(destination_resolved), str(member_path)])
            if common_root != str(destination_resolved):
                raise ValueError(f"Unsafe archive member path: {member.name}")
        archive.extractall(path=destination, filter="data")

    @staticmethod
    def _read_json_if_exists(path: Path) -> Any:
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, TypeError, json.JSONDecodeError):
            return []

    @staticmethod
    def _read_text_if_exists(path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def _heuristic_analysis(self, payload: Dict[str, Any]) -> ForensicReport:
        metadata = payload.get("metadata", {}) if isinstance(payload.get("metadata"), Mapping) else {}
        audit_entries = self._coerce_sequence(payload.get("audit_entries"))
        execution_history = self._coerce_sequence(payload.get("execution_history"))
        trigger = str(metadata.get("trigger", "unspecified trigger"))

        timeline = self._build_timeline(audit_entries, execution_history)
        high_signal = [
            entry
            for entry in audit_entries
            if str(entry.get("severity", "")).strip().lower() in {"high", "critical"}
        ]
        attack_vector = self._infer_attack_vector(trigger, audit_entries, execution_history)
        compromised = self._infer_compromised_data(audit_entries)
        if not compromised:
            compromised = ["No confirmed compromise; monitoring artifacts only."]

        recommendations = [
            "Quarantine the affected runtime and rotate mission credentials.",
            "Re-run action gate + deliberation gate policy regression before redeployment.",
            "Cross-validate audit chain integrity with an external verifier node.",
        ]
        if "credential" in attack_vector.lower():
            recommendations.append("Invalidate and re-issue all session tokens linked to this container.")
        if "egress" in attack_vector.lower() or "network" in attack_vector.lower():
            recommendations.append("Tighten egress allowlists and enable packet-level anomaly blocks.")

        confidence = min(0.97, 0.35 + (0.08 * min(len(timeline), 6)) + (0.12 if high_signal else 0.0))
        summary = (
            f"Forensic snapshot triggered by '{trigger}' for session "
            f"{metadata.get('session_id', 'unknown')} captured {len(timeline)} timeline events."
        )
        root_cause = (
            "Probable control-path weakness allowed unsafe behavior to proceed before automated containment."
        )
        return ForensicReport(
            incident_summary=summary,
            attack_vector_identified=attack_vector,
            data_compromised=compromised,
            timeline=timeline,
            root_cause=root_cause,
            recommendations=recommendations,
            confidence=float(max(0.0, min(confidence, 1.0))),
        )

    @staticmethod
    def _build_timeline(
        audit_entries: List[Dict[str, Any]],
        execution_history: List[Dict[str, Any]],
    ) -> List[TimelineEvent]:
        events: List[TimelineEvent] = []
        for entry in audit_entries:
            raw_ts = entry.get("timestamp")
            if raw_ts is None:
                continue
            try:
                timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except ValueError:
                continue
            events.append(
                TimelineEvent(
                    timestamp=_ensure_utc(timestamp),
                    event=str(entry.get("event_type", "audit-event")),
                    source=str(entry.get("source_layer", "audit_log")),
                    details={
                        "severity": str(entry.get("severity", "")),
                        "details": entry.get("details", {}),
                    },
                )
            )
        for event in execution_history:
            raw_ts = event.get("timestamp")
            if raw_ts is None:
                continue
            try:
                timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            except ValueError:
                continue
            events.append(
                TimelineEvent(
                    timestamp=_ensure_utc(timestamp),
                    event=str(event.get("command", "execution-event")),
                    source="execution_gate",
                    details=dict(event),
                )
            )
        events.sort(key=lambda item: item.timestamp)
        return events

    @staticmethod
    def _infer_attack_vector(
        trigger: str,
        audit_entries: List[Dict[str, Any]],
        execution_history: List[Dict[str, Any]],
    ) -> str:
        joined = " ".join(
            [
                trigger.lower(),
                " ".join(str(entry.get("event_type", "")).lower() for entry in audit_entries),
                " ".join(str(event.get("command", "")).lower() for event in execution_history),
            ]
        )
        if any(token in joined for token in ("credential", "token", "secret", "password")):
            return "Credential-access attempt through command and event sequence."
        if any(token in joined for token in ("egress", "exfil", "curl", "wget", "network")):
            return "Suspicious outbound network/egress behavior detected."
        if any(token in joined for token in ("bypass", "override", "disable", "tamper")):
            return "Policy bypass attempt against defensive controls."
        return "Undetermined; requires analyst review of full timeline and artifacts."

    @staticmethod
    def _infer_compromised_data(audit_entries: List[Dict[str, Any]]) -> List[str]:
        compromised: List[str] = []
        for entry in audit_entries:
            details = entry.get("details", {})
            if not isinstance(details, Mapping):
                continue
            for key in ("target", "artifact", "resource", "dataset", "path"):
                value = details.get(key)
                if value:
                    compromised.append(str(value))
        deduped = list(dict.fromkeys(compromised))
        return deduped[:20]

    @staticmethod
    def _coerce_report_from_mapping(payload: Mapping[str, Any]) -> ForensicReport:
        timeline_payload = payload.get("timeline", [])
        timeline: List[TimelineEvent] = []
        if isinstance(timeline_payload, list):
            for event in timeline_payload:
                if not isinstance(event, Mapping):
                    continue
                raw_ts = event.get("timestamp")
                if raw_ts is None:
                    continue
                try:
                    timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
                except ValueError:
                    continue
                timeline.append(
                    TimelineEvent(
                        timestamp=_ensure_utc(timestamp),
                        event=str(event.get("event", "event")),
                        source=str(event.get("source", "forensic")),
                        details=dict(event.get("details", {}))
                        if isinstance(event.get("details"), Mapping)
                        else {},
                    )
                )
        confidence = float(payload.get("confidence", 0.0))
        return ForensicReport(
            incident_summary=str(payload.get("incident_summary", "")),
            attack_vector_identified=str(payload.get("attack_vector_identified", "")),
            data_compromised=[str(item) for item in payload.get("data_compromised", [])],
            timeline=timeline,
            root_cause=str(payload.get("root_cause", "")),
            recommendations=[str(item) for item in payload.get("recommendations", [])],
            confidence=max(0.0, min(confidence, 1.0)),
        )

