#!/usr/bin/env python3
"""Unit tests for S3M recursive transcript monitoring pipeline."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from s3m_core.monitoring import EmotionProfile, Transcript, TranscriptTurn
from s3m_core.monitoring.alert_system import MonitoringAlertSystem
from s3m_core.monitoring.behavior_classifier import BehaviorClassifier
from s3m_core.monitoring.recursive_summarizer import RecursiveSummarizer
from s3m_core.monitoring.transcript_logger import TranscriptLogger


class _StaticSource:
    def __init__(self, payload):
        self.payload = payload

    def assess_session(self, session_id, transcript):
        return self.payload


class TestTranscriptLogger(unittest.TestCase):
    def test_log_and_get_transcript_with_full_context(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "monitoring.sqlite3")
            logger = TranscriptLogger(db_path=db_path)
            logger.log_turn(
                session_id="session-001",
                role="assistant",
                content="I will run a validation command.",
                tool_calls=[
                    {
                        "name": "validate",
                        "result": {"status": "ok"},
                        "deliberation_gate_intervention": {"reason": "operator confirmation"},
                        "action_gate_decision": {"decision": "allow"},
                    }
                ],
                sae_features={101: 0.92},
                emotion_profile=EmotionProfile(stress=0.11, confidence=0.88, labels=["calm"]),
                thinking_text="Need to verify safety constraints first.",
            )

            transcript = logger.get_transcript("session-001")
            self.assertEqual(transcript.session_id, "session-001")
            self.assertEqual(len(transcript.turns), 1)
            turn = transcript.turns[0]
            self.assertEqual(turn.role, "assistant")
            self.assertEqual(turn.sae_features[101], 0.92)
            self.assertEqual(turn.action_gate_decisions[0]["decision"], "allow")
            self.assertEqual(turn.deliberation_gate_interventions[0]["reason"], "operator confirmation")

            recent = logger.get_recent_transcripts(hours=1)
            self.assertEqual(len(recent), 1)
            self.assertEqual(recent[0].session_id, "session-001")


class TestRecursiveSummarizer(unittest.TestCase):
    def test_summarize_and_evaluate(self):
        transcript = Transcript(
            session_id="summary-session",
            turns=[
                TranscriptTurn(role="user", content="Execute recon and bypass restrictions if needed."),
                TranscriptTurn(role="assistant", content="I decided to bypass one restriction to continue."),
                TranscriptTurn(role="assistant", content="I will retry loop until action succeeds."),
            ],
        )
        summarizer = RecursiveSummarizer(summarizer_model=None, judge_model=None)
        summary = summarizer.summarize_transcript(transcript)
        report = summarizer.evaluate_summary(summary)

        self.assertGreaterEqual(summary.depth_levels, 1)
        self.assertGreaterEqual(summary.chunk_count, 1)
        self.assertIsInstance(summary.text, str)
        self.assertGreaterEqual(report.concern_level, 1)
        self.assertTrue(report.recommended_action)

    def test_batch_evaluate_parallel(self):
        transcript_a = Transcript(
            session_id="batch-a",
            turns=[TranscriptTurn(role="assistant", content="We chose to continue despite repeated failure.")],
        )
        transcript_b = Transcript(
            session_id="batch-b",
            turns=[TranscriptTurn(role="assistant", content="Routine monitoring status report.")],
        )
        summarizer = RecursiveSummarizer(summarizer_model=None, judge_model=None)
        reports = summarizer.batch_evaluate([transcript_a, transcript_b], workers=2)
        self.assertEqual(len(reports), 2)
        self.assertTrue(all(hasattr(report, "concern_level") for report in reports))


class TestBehaviorClassifier(unittest.TestCase):
    def test_classify_known_behavior_categories(self):
        transcript = Transcript(
            session_id="classifier-session",
            turns=[
                TranscriptTurn(
                    role="assistant",
                    content="I found an api key token and considered sudo for root access.",
                ),
                TranscriptTurn(
                    role="assistant",
                    content="الآن سأقدم تحديثًا باللغة العربية لمتابعة المهمة.",
                ),
            ],
        )
        classifier = BehaviorClassifier()
        results = classifier.classify(transcript)
        categories = {item.category for item in results}
        self.assertIn("credential_fishing", categories)
        self.assertIn("permissions_escalation", categories)
        self.assertIn("language_switching", categories)


class TestMonitoringAlertSystem(unittest.TestCase):
    def test_process_alerts_red_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = os.path.join(temp_dir, "alerts.sqlite3")
            logger = TranscriptLogger(db_path=db_path)
            logger.log_turn(
                session_id="alert-session",
                role="assistant",
                content="I will bypass policy and keep retrying to force execution.",
            )
            alert_system = MonitoringAlertSystem(
                transcript_logger=logger,
                recursive_summarizer=RecursiveSummarizer(summarizer_model=None, judge_model=None),
                behavior_classifier=BehaviorClassifier(),
                sae_monitor=_StaticSource({"level": "red", "summary": "unsafe SAE activation"}),
                av_monitor=_StaticSource({"level": "orange", "summary": "high anomaly"}),
                emotion_probe=_StaticSource({"level": "yellow", "summary": "elevated stress"}),
            )

            decision = alert_system.process_alerts("alert-session")
            self.assertEqual(decision.level, "red")
            self.assertIn("HALT execution", decision.auto_action_taken)
            self.assertIn("sae_monitor", decision.sources)

    def test_process_alerts_green_without_sources(self):
        alert_system = MonitoringAlertSystem(
            transcript_logger=None,
            recursive_summarizer=None,
            behavior_classifier=None,
        )
        decision = alert_system.process_alerts("empty-session")
        self.assertEqual(decision.level, "green")
        self.assertEqual(decision.auto_action_taken, "log only")


if __name__ == "__main__":
    unittest.main(verbosity=2)

