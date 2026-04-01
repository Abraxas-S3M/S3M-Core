"""Cyber training manager for SOC analyst exercise generation and scoring."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import uuid4

from src.threat_detection.models import ThreatCategory, ThreatEvent, ThreatLevel, ThreatSource


class CyberTrainingManager:
    """Builds synthetic cyber scenarios and evaluates SOC handling quality."""

    def __init__(self, soc_manager: Optional[object] = None, auto_create_manager: bool = True) -> None:
        if soc_manager is None:
            if not auto_create_manager:
                self.soc_manager = None
            else:
                from services.cyber.soc_manager import SOCManager
                self.soc_manager = SOCManager()
        else:
            self.soc_manager = soc_manager
        self._history: List[dict] = []
        self._scenario_types = ["brute_force", "malware", "data_exfil", "ransomware"]

    def _build_event(
        self,
        title: str,
        description: str,
        level: ThreatLevel,
        raw_data: dict,
        confidence: float = 0.8,
    ) -> ThreatEvent:
        return ThreatEvent(
            source=ThreatSource.MANUAL,
            level=level,
            category=ThreatCategory.CYBER,
            title=title,
            description=description,
            raw_data=raw_data,
            confidence=confidence,
            classification="UNCLASSIFIED - FOUO",
        )

    def create_exercise(self, scenario_type: str = "brute_force") -> dict:
        scenario = scenario_type.strip().lower()
        if scenario not in self._scenario_types:
            raise ValueError(f"Unsupported scenario_type: {scenario_type}")
        events: List[ThreatEvent] = []
        now = datetime.now(timezone.utc)

        if scenario == "brute_force":
            ips = ["203.0.113.10", "203.0.113.20", "203.0.113.30"]
            for i in range(50):
                ip = ips[i % len(ips)]
                events.append(
                    self._build_event(
                        title="SSH brute force attempt",
                        description=f"Repeated failed SSH authentication from {ip}",
                        level=ThreatLevel.MEDIUM if i < 40 else ThreatLevel.HIGH,
                        raw_data={
                            "src_ip": ip,
                            "dest_ip": "10.0.0.5",
                            "service": "ssh",
                            "attempt": i + 1,
                            "window": "10m",
                            "timestamp_hint": (now + timedelta(seconds=i * 12)).isoformat(),
                        },
                        confidence=0.72,
                    )
                )
        elif scenario == "malware":
            hashes = [
                "a" * 64,
                "b" * 64,
                "c" * 64,
            ]
            for i in range(20):
                h = hashes[i % len(hashes)]
                events.append(
                    self._build_event(
                        title="Malware indicator detected",
                        description=f"Malware file hash observed on endpoint: {h}",
                        level=ThreatLevel.HIGH,
                        raw_data={
                            "sha256": h,
                            "host": f"endpoint-{(i % 4) + 1}",
                            "lateral_movement": i > 8,
                            "c2_callback": i > 12,
                        },
                        confidence=0.86,
                    )
                )
        elif scenario == "data_exfil":
            for i in range(25):
                events.append(
                    self._build_event(
                        title="Potential data exfiltration",
                        description="Suspicious outbound transfer and DNS tunneling behavior",
                        level=ThreatLevel.HIGH if i > 5 else ThreatLevel.MEDIUM,
                        raw_data={
                            "src_host": "db-gateway-2",
                            "dest_ip": "198.51.100.55",
                            "dns_query": f"chunk{i}.exfil.example.net",
                            "bytes_transferred": 500000 + i * 25000,
                        },
                        confidence=0.82,
                    )
                )
        elif scenario == "ransomware":
            sequence = [
                ("Phishing email detected", ThreatLevel.MEDIUM),
                ("Payload execution on endpoint", ThreatLevel.HIGH),
                ("Rapid file encryption behavior", ThreatLevel.CRITICAL),
                ("Ransom note created", ThreatLevel.CRITICAL),
            ]
            for i in range(24):
                title, level = sequence[i % len(sequence)]
                events.append(
                    self._build_event(
                        title=title,
                        description=f"Ransomware kill-chain event stage {i % len(sequence)}",
                        level=level,
                        raw_data={
                            "host": f"finance-node-{(i % 3) + 1}",
                            "user": f"user{(i % 5) + 1}@s3m.local",
                            "note_path": "/tmp/README_RESTORE.txt" if "note" in title.lower() else "",
                        },
                        confidence=0.9 if level == ThreatLevel.CRITICAL else 0.78,
                    )
                )

        exercise = {
            "exercise_id": str(uuid4()),
            "scenario_type": scenario,
            "events": events,
            "created_at": now.isoformat(),
        }
        return exercise

    def run_exercise(self, events: List[ThreatEvent]) -> dict:
        if self.soc_manager is None:
            raise ValueError("CyberTrainingManager has no SOCManager bound for run_exercise")
        started = datetime.now(timezone.utc)
        result = self.soc_manager.process_batch(events)
        finished = datetime.now(timezone.utc)
        elapsed = (finished - started).total_seconds()
        scorecard = {
            "exercise_id": str(uuid4()),
            "started_at": started.isoformat(),
            "completed_at": finished.isoformat(),
            "duration_seconds": round(elapsed, 3),
            "events_processed": len(events),
            "cases_created": int(result.get("cases_created", 0)),
            "playbooks_triggered": int(result.get("playbooks_triggered", 0)),
            "analyst_response_time_seconds": round(elapsed / max(len(events), 1), 3),
            "pipeline": result,
        }
        self._history.append(scorecard)
        if len(self._history) > 200:
            del self._history[:-200]
        return scorecard

    def evaluate_response(self, exercise_id: str) -> dict:
        for item in reversed(self._history):
            if item.get("exercise_id") == exercise_id:
                events = item.get("events_processed", 0)
                cases = item.get("cases_created", 0)
                playbooks = item.get("playbooks_triggered", 0)
                score = min(100.0, 40.0 + (cases * 1.5) + (playbooks * 2.5) + min(events, 50) * 0.3)
                # Tactical note: simulated LLM evaluation keeps training workflow air-gapped.
                return {
                    "score": round(score, 2),
                    "strengths": [
                        "Timely case generation from threat stream",
                        "Automated playbook execution under offline constraints",
                    ],
                    "improvements": [
                        "Increase analyst assignment speed for medium-severity cases",
                        "Expand IOC enrichment coverage for domains and emails",
                    ],
                    "recommendations": (
                        "Maintain containment-first SOP, validate ATT&CK mappings per incident, "
                        "and run follow-up tabletop for escalation handoff quality."
                    ),
                }
        return {
            "score": 0.0,
            "strengths": [],
            "improvements": ["Exercise not found in local training history"],
            "recommendations": "Re-run exercise and evaluate again.",
        }

    def list_exercise_types(self) -> List[str]:
        return list(self._scenario_types)

    def get_exercise_history(self) -> List[dict]:
        return list(reversed(self._history))
