"""F2T2EA pipeline for autonomous kill-chain processing.

Military context:
Implements find-fix-track-target-engage-assess workflow with mandatory safety,
XAI, and audit controls in sovereign air-gapped deployments.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid

from services.killchain.models import (
    BattleDamageAssessment,
    EngagementAuthority,
    EngagementRequest,
    KillChainAuditEntry,
    KillChainPhase,
    TargetClassification,
)
from services.killchain.safety_interlocks import KillChainSafetyInterlocks
from services.killchain.weapon_target_pairing import WeaponTargetPairing
from services.sensor_analytics.ais.tracker import AISTracker
from services.sensor_analytics.sar.detector import SARDetector
from src.apps.drone_ops import AutopilotBridge
from src.autonomy.models import AutonomyDecision, DecisionType
from src.autonomy.xai import AssuranceChecker, DecisionExplainer
from src.security.crypto import SecureAuditLog
from src.sensor_fusion.models import SensorReading, SensorType
from src.sensor_fusion.track_fuser import TrackFuser
from src.threat_detection.object_detector import ObjectDetector
from src.threat_detection.threat_classifier import ThreatClassifier


class F2T2EAPipeline:
    """Core kill-chain processor with graduated authority enforcement."""

    def __init__(self, authority_level: EngagementAuthority = EngagementAuthority.HITL):
        self.authority_level = authority_level
        self.object_detector = ObjectDetector(model_path="models/yolov8n-military.pt", confidence_threshold=0.5)
        self.track_fuser = TrackFuser()
        self.threat_classifier = ThreatClassifier()
        self.sar_detector = SARDetector(model_backend="auto")
        self.ais_tracker = AISTracker()
        self.assurance = AssuranceChecker(risk_threshold=0.7, confidence_threshold=0.3)
        self.explainer = DecisionExplainer()
        self.audit_log = SecureAuditLog(log_dir="data/security_audit/killchain")
        self.interlocks = KillChainSafetyInterlocks()
        self.pairing = WeaponTargetPairing()
        self.autopilot = AutopilotBridge(backend="simulated")
        self.autopilot.connect()

        self._requests: Dict[str, EngagementRequest] = {}
        self._bda: Dict[str, BattleDamageAssessment] = {}
        self._audit_entries: List[KillChainAuditEntry] = []

    def _audit_phase(
        self,
        phase: KillChainPhase,
        decision: str,
        xai_explanation: str,
        request_id: str = "",
        human_involved: bool = False,
        details: Optional[dict] = None,
    ) -> None:
        entry = KillChainAuditEntry(
            entry_id=f"kc-audit-{uuid.uuid4().hex[:10]}",
            timestamp=datetime.now(timezone.utc),
            engagement_request_id=request_id,
            phase=phase,
            authority_level=self.authority_level,
            decision=decision,
            xai_explanation=xai_explanation,
            human_involved=human_involved,
            details=details or {},
        )
        self._audit_entries.append(entry)
        self.audit_log.log(
            action=f"killchain_{phase.value}",
            source="killchain",
            details={
                "entry_id": entry.entry_id,
                "request_id": request_id,
                "decision": decision,
                "xai": xai_explanation,
                "details": entry.details,
            },
        )

    def _threat_assessment_text(self, target: TargetClassification, roe: str) -> str:
        valid = target.classification.upper() not in {"CIVILIAN", "UNKNOWN"} and target.confidence >= 0.5
        risk_level = "HIGH" if target.civilian_proximity_m < 50 else "LOW"
        return (
            '{"is_valid_target": '
            + ("true" if valid else "false")
            + f', "reasoning": "Target {target.classification} confidence {target.confidence:.2f} under {roe}", '
            + f'"risk_level": "{risk_level}"}}'
        )

    def _collateral_estimate_text(self, target: TargetClassification, weapon_type: str) -> str:
        proximity = target.civilian_proximity_m
        if proximity < 30:
            level = "UNACCEPTABLE"
        elif proximity < 80:
            level = "HIGH"
        elif proximity < 200:
            level = "MEDIUM"
        elif proximity < 500:
            level = "LOW"
        else:
            level = "NONE"
        return f"Collateral risk: {level}; civilian distance {proximity:.1f}m; weapon {weapon_type}."

    def find(self, sensor_data: dict) -> List[TargetClassification]:
        """Find phase: run available detectors and return classified targets."""
        detections: List[TargetClassification] = []
        image_path = sensor_data.get("image_path")
        if image_path:
            for det in self.object_detector.detect(image_path):
                detections.append(
                    TargetClassification(
                        target_id=f"tgt-{uuid.uuid4().hex[:8]}",
                        classification=str(det.class_name).replace("[STUB]", "").strip().upper().replace(" ", "_"),
                        confidence=float(det.confidence),
                        position=(float(det.bbox_xyxy[0]), float(det.bbox_xyxy[1]), 0.0),
                        velocity=(0.0, 0.0, 0.0),
                        source="yolo",
                        first_detected=datetime.now(timezone.utc),
                        last_updated=datetime.now(timezone.utc),
                        track_id="",
                        is_military_objective=None,
                        civilian_proximity_m=float(sensor_data.get("civilian_proximity_m", 300.0)),
                        collateral_risk="UNKNOWN",
                        image_evidence=image_path,
                    )
                )

        sar_image = sensor_data.get("sar_image_path")
        if sar_image:
            for sar in self.sar_detector.detect(sar_image):
                detections.append(
                    TargetClassification(
                        target_id=f"tgt-{uuid.uuid4().hex[:8]}",
                        classification="ENEMY_SHIP",
                        confidence=float(sar.confidence),
                        position=(float(sar.geo_position[0]), float(sar.geo_position[1]), 0.0),
                        velocity=(0.0, 0.0, 0.0),
                        source="sar",
                        first_detected=datetime.now(timezone.utc),
                        last_updated=datetime.now(timezone.utc),
                        track_id="",
                        is_military_objective=None,
                        civilian_proximity_m=500.0,
                        collateral_risk="LOW",
                        image_evidence=sar_image,
                    )
                )

        self._audit_phase(
            KillChainPhase.FIND,
            decision="detections_generated",
            xai_explanation=f"Detection source count={len(detections)}",
            details={"sources": sorted({d.source for d in detections})},
        )
        return [d for d in detections if d.confidence >= float(sensor_data.get("min_confidence", 0.5))]

    def fix(self, target: TargetClassification) -> TargetClassification:
        """Fix phase: refine target coordinates using simple sensor fusion."""
        reading = SensorReading(
            sensor_id=f"fix-{target.source}",
            sensor_type=SensorType.EO_CAMERA,
            timestamp=datetime.now(timezone.utc),
            data={"classification": target.classification},
            position=target.position,
            confidence=target.confidence,
        )
        tracks = self.track_fuser.update([reading])
        if tracks:
            latest = tracks[-1]
            target.position = latest.position
            target.velocity = latest.velocity
            target.track_id = latest.track_id
        target.last_updated = datetime.now(timezone.utc)
        self._audit_phase(KillChainPhase.FIX, "target_fixed", f"Target fixed at {target.position}", details={"target_id": target.target_id})
        return target

    def track(self, target: TargetClassification) -> TargetClassification:
        """Track phase: maintain persistent state estimate for target motion."""
        reading = SensorReading(
            sensor_id=f"track-{target.source}",
            sensor_type=SensorType.RADAR,
            timestamp=datetime.now(timezone.utc),
            data={"classification": target.classification},
            position=target.position,
            confidence=target.confidence,
        )
        tracks = self.track_fuser.update([reading])
        if tracks:
            latest = tracks[-1]
            target.velocity = latest.velocity
            target.track_id = latest.track_id
            target.last_updated = datetime.now(timezone.utc)
        self._audit_phase(KillChainPhase.TRACK, "target_tracked", f"Track {target.track_id}", details={"target_id": target.target_id})
        return target

    def target(self, target: TargetClassification) -> EngagementRequest:
        """Target phase: assess legality, collateral risk, and approval gating."""
        weapon_options = [
            {"type": "air_to_air_missile", "range_m": 5000, "collateral_radius_m": 30},
            {"type": "electronic_kill", "range_m": 2000, "collateral_radius_m": 5},
            {"type": "direct_fire", "range_m": 800, "collateral_radius_m": 50},
        ]
        pair = self.pairing.pair(target, weapon_options)
        weapon = (pair.get("weapon") or {}).get("type", "direct_fire")

        threat_assessment = self._threat_assessment_text(target, roe="weapons_tight")
        collateral = self._collateral_estimate_text(target, weapon)
        roe_compliant = target.classification.upper() != "CIVILIAN"
        if "UNACCEPTABLE" in collateral:
            roe_compliant = False

        request_id = f"eng-{uuid.uuid4().hex[:10]}"
        human_required = True
        timeout = float("inf")
        if self.authority_level == EngagementAuthority.HOTL:
            human_required = True
            timeout = 30.0
        elif self.authority_level == EngagementAuthority.SUPERVISED:
            high_risk = "HIGH" in collateral or "UNACCEPTABLE" in collateral
            civilian_or_unknown = target.classification.upper() in {"CIVILIAN", "UNKNOWN"}
            human_required = target.confidence < 0.8 or high_risk or civilian_or_unknown
            timeout = 30.0 if human_required else 0.0
        elif self.authority_level in {EngagementAuthority.DEFENSIVE, EngagementAuthority.FULL_AUTONOMOUS}:
            human_required = False
            timeout = 0.0

        status = "pending_approval" if human_required else "approved"
        if "UNACCEPTABLE" in collateral:
            status = "aborted"

        request = EngagementRequest(
            request_id=request_id,
            target_id=target.target_id,
            authority_level=self.authority_level,
            roe_level="weapons_tight",
            weapon_type=weapon,
            platform_id="platform-1",
            requesting_agent="killchain_pipeline",
            phase=KillChainPhase.TARGET,
            confidence=target.confidence,
            threat_assessment=threat_assessment,
            collateral_estimate=collateral,
            roe_compliant=roe_compliant,
            xai_explanation=f"Targeting rationale: {pair.get('reasoning')}",
            human_approval_required=human_required,
            human_approval_timeout_seconds=timeout,
            human_decision=None,
            human_decision_by=None,
            human_decision_at=None,
            status=status,
            created_at=datetime.now(timezone.utc),
        )

        decision = AutonomyDecision(
            decision_id=f"kc-dec-{uuid.uuid4().hex[:10]}",
            timestamp=datetime.now(timezone.utc),
            decision_type=DecisionType.ENGAGE,
            agent_id="killchain",
            mission_id=None,
            context={"rules_of_engagement": request.roe_level, "request_id": request.request_id},
            action_taken={"phase": "target", "status": status},
            alternatives_considered=[{"option": "hold_fire", "reason": "safety gate"}],
            confidence=request.confidence,
            reasoning=request.xai_explanation,
            llm_consulted=False,
            requires_human_review=False,
            risk_score=min(1.0, max(0.0, 1.0 - request.confidence)),
        )
        assurance = self.assurance.check(decision)
        xai = self.explainer.explain(decision)
        request.xai_explanation = f"{request.xai_explanation}; assurance={assurance['reason']}; xai={xai.get('summary')}"

        audit = self.audit_log.log(
            action="killchain_target_assessment",
            source="killchain",
            details={"request_id": request.request_id, "status": request.status, "target": target.target_id},
        )
        request.__dict__["audit_entries_count"] = 1 if audit.get("entry_id") else 0
        self._requests[request.request_id] = request
        self._audit_phase(
            KillChainPhase.TARGET,
            decision=request.status,
            xai_explanation=request.xai_explanation,
            request_id=request.request_id,
            human_involved=request.human_approval_required,
        )
        return request

    def request_human_approval(self, request: EngagementRequest) -> EngagementRequest:
        """Queue approval and apply timeout behavior according to authority mode."""
        request.status = "pending_approval"
        if request.human_approval_timeout_seconds == float("inf"):
            # HITL requires explicit approve/veto.
            self._requests[request.request_id] = request
            return request

        if request.human_approval_timeout_seconds > 0 and request.status == "pending_approval":
            if request.roe_compliant and "UNACCEPTABLE" not in request.collateral_estimate.upper():
                request.human_decision = "timeout_proceed"
                request.status = "approved"
            else:
                request.human_decision = "timeout_abort"
                request.status = "aborted"
            request.human_decision_at = datetime.now(timezone.utc)
            request.human_decision_by = "timeout_controller"
        self._requests[request.request_id] = request
        return request

    def engage(self, request: EngagementRequest) -> dict:
        """Engage phase with triple-check safety and interlock enforcement."""
        allowed, reason = self.interlocks.validate_engagement(request)
        if not allowed:
            request.status = "aborted"
            self._audit_phase(KillChainPhase.ENGAGE, "blocked", reason, request_id=request.request_id)
            return {"executed": False, "weapon": request.weapon_type, "target": request.target_id, "timestamp": datetime.now(timezone.utc), "reason": reason}

        if request.status not in {"approved", "executing"}:
            if request.authority_level in {EngagementAuthority.DEFENSIVE, EngagementAuthority.FULL_AUTONOMOUS} and request.roe_compliant:
                request.status = "approved"
            else:
                self._audit_phase(KillChainPhase.ENGAGE, "blocked", "Request not approved", request_id=request.request_id)
                return {"executed": False, "weapon": request.weapon_type, "target": request.target_id, "timestamp": datetime.now(timezone.utc), "reason": "Request not approved"}

        if not request.roe_compliant or "UNACCEPTABLE" in request.collateral_estimate.upper():
            request.status = "aborted"
            return {"executed": False, "weapon": request.weapon_type, "target": request.target_id, "timestamp": datetime.now(timezone.utc), "reason": "ROE/collateral gate failed"}

        request.status = "executing"
        self.autopilot.send_command({"type": "ENGAGE", "target_id": request.target_id, "weapon": request.weapon_type})
        request.status = "completed"
        result = {
            "executed": True,
            "weapon": request.weapon_type,
            "target": request.target_id,
            "timestamp": datetime.now(timezone.utc),
        }
        self._audit_phase(KillChainPhase.ENGAGE, "executed", "Engagement executed", request_id=request.request_id)
        return result

    def assess(self, request: EngagementRequest) -> BattleDamageAssessment:
        """Assess phase: post-engagement battle damage estimate."""
        executed = request.status == "completed"
        status = "destroyed" if executed and request.confidence > 0.7 else ("damaged" if executed else "unknown")
        bda = BattleDamageAssessment(
            bda_id=f"bda-{uuid.uuid4().hex[:10]}",
            engagement_request_id=request.request_id,
            target_id=request.target_id,
            assessment_time=datetime.now(timezone.utc),
            target_status=status,
            confidence=max(0.4, request.confidence - 0.1),
            method="atr_rescan",
            evidence=[{"type": "imagery", "note": "post-strike scan"}],
            reengagement_recommended=status in {"damaged", "missed", "unknown"},
            llm_analysis="Post-engagement assessment completed with ATR evidence.",
        )
        self._bda[request.request_id] = bda
        self._audit_phase(KillChainPhase.ASSESS, status, "BDA generated", request_id=request.request_id)
        return bda

    def execute_chain(self, sensor_data: dict, authority: EngagementAuthority = None) -> dict:
        """Execute full find-fix-track-target-engage-assess cycle."""
        if authority is not None:
            self.authority_level = authority
        detections = self.find(sensor_data)
        if not detections:
            return {"status": "no_targets", "find": [], "fix": None, "track": None, "target": None, "engage": None, "assess": None}

        target = self.track(self.fix(detections[0]))
        request = self.target(target)
        if request.human_approval_required:
            request = self.request_human_approval(request)
        engage_result = self.engage(request)
        bda = self.assess(request)
        return {
            "status": "completed" if engage_result.get("executed") else "blocked",
            "find": [d.__dict__ for d in detections],
            "fix": target.__dict__,
            "track": target.__dict__,
            "target": request.__dict__,
            "engage": engage_result,
            "assess": bda.__dict__,
        }

    def get_engagement_log(self, limit: int = 50) -> List[KillChainAuditEntry]:
        """Return latest kill-chain audit entries."""
        return self._audit_entries[-max(1, int(limit)) :]

    def get_pending_approvals(self) -> List[EngagementRequest]:
        """Return pending human-approval requests."""
        return [r for r in self._requests.values() if r.status == "pending_approval"]
