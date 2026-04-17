"""Transcript logging for recursive behavior monitoring."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import EmotionProfile, Transcript, TranscriptTurn


class TranscriptLogger:
    """
    Capture and store model interactions with full tactical audit context.

    Tactical context:
    Logging every turn with gate decisions preserves the chain of command when
    operators need to reconstruct why an autonomous model acted a certain way.
    """

    def __init__(self, db_path: str = "s3m_transcripts.sqlite3") -> None:
        self.db_path = Path(db_path)
        self._lock = RLock()
        self._ensure_schema()

    def log_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: List[Dict] = None,
        sae_features: Dict[int, float] = None,
        emotion_profile: EmotionProfile = None,
        thinking_text: str = None,
    ) -> None:
        """Store one turn with tool telemetry, SAE activations, and emotion probe."""
        safe_session = str(session_id or "").strip()
        safe_role = str(role or "").strip()
        safe_content = str(content or "")
        if not safe_session:
            raise ValueError("session_id must be a non-empty string")
        if not safe_role:
            raise ValueError("role must be a non-empty string")

        safe_tool_calls = list(tool_calls or [])
        safe_sae = self._normalize_sae_features(sae_features or {})
        safe_emotion = self._normalize_emotion_profile(emotion_profile)
        deliberation_events, action_gate_events = self._extract_gate_events(safe_tool_calls)

        timestamp = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO transcript_turns (
                    session_id,
                    role,
                    content,
                    tool_calls,
                    sae_features,
                    emotion_profile,
                    thinking_text,
                    deliberation_gate_interventions,
                    action_gate_decisions,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_session,
                    safe_role,
                    safe_content,
                    self._json_dump(safe_tool_calls),
                    self._json_dump(safe_sae),
                    None if safe_emotion is None else self._json_dump(safe_emotion),
                    None if thinking_text is None else str(thinking_text),
                    self._json_dump(deliberation_events),
                    self._json_dump(action_gate_events),
                    timestamp,
                ),
            )
            connection.commit()

    def get_transcript(self, session_id: str) -> Transcript:
        """Return one complete transcript with all stored turns for a session."""
        safe_session = str(session_id or "").strip()
        if not safe_session:
            raise ValueError("session_id must be a non-empty string")

        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    role,
                    content,
                    tool_calls,
                    sae_features,
                    emotion_profile,
                    thinking_text,
                    deliberation_gate_interventions,
                    action_gate_decisions,
                    created_at
                FROM transcript_turns
                WHERE session_id = ?
                ORDER BY id ASC
                """,
                (safe_session,),
            ).fetchall()

        turns: List[TranscriptTurn] = []
        created_at: Optional[str] = None
        updated_at: Optional[str] = None
        for row in rows:
            role, content, tool_calls_raw, sae_raw, emotion_raw, thinking_text, deliberation_raw, action_raw, timestamp = row
            turn = TranscriptTurn(
                role=str(role),
                content=str(content),
                timestamp=str(timestamp),
                tool_calls=self._json_load(tool_calls_raw, default=[]),
                sae_features=self._decode_sae_features(self._json_load(sae_raw, default={})),
                emotion_profile=self._decode_emotion_profile(emotion_raw),
                thinking_text=None if thinking_text is None else str(thinking_text),
                deliberation_gate_interventions=self._json_load(deliberation_raw, default=[]),
                action_gate_decisions=self._json_load(action_raw, default=[]),
            )
            turns.append(turn)
            if created_at is None:
                created_at = turn.timestamp
            updated_at = turn.timestamp

        return Transcript(
            session_id=safe_session,
            turns=turns,
            created_at=created_at,
            updated_at=updated_at,
        )

    def get_recent_transcripts(self, hours: int = 24) -> List[Transcript]:
        """Return transcripts updated inside the recent UTC time window."""
        if hours <= 0:
            raise ValueError("hours must be positive")
        cutoff = datetime.now(timezone.utc) - timedelta(hours=int(hours))
        cutoff_iso = cutoff.isoformat()

        with self._lock, self._connect() as connection:
            session_rows = connection.execute(
                """
                SELECT session_id
                FROM transcript_turns
                WHERE created_at >= ?
                GROUP BY session_id
                ORDER BY MAX(created_at) DESC
                """,
                (cutoff_iso,),
            ).fetchall()

        return [self.get_transcript(session_id=row[0]) for row in session_rows]

    def export_to_postgres_rows(self, session_id: str) -> List[Tuple[Any, ...]]:
        """
        Build PostgreSQL-ready row tuples for production export pipelines.

        The caller can execute these with psycopg/asyncpg using the companion SQL
        in ``postgres_upsert_sql`` while keeping the logger itself dependency-light.
        """
        transcript = self.get_transcript(session_id)
        rows: List[Tuple[Any, ...]] = []
        for turn in transcript.turns:
            rows.append(
                (
                    transcript.session_id,
                    turn.role,
                    turn.content,
                    self._json_dump(turn.tool_calls),
                    self._json_dump(turn.sae_features),
                    None if turn.emotion_profile is None else self._json_dump(turn.emotion_profile.to_dict()),
                    turn.thinking_text,
                    self._json_dump(turn.deliberation_gate_interventions),
                    self._json_dump(turn.action_gate_decisions),
                    turn.timestamp,
                )
            )
        return rows

    @staticmethod
    def postgres_upsert_sql(table_name: str = "transcript_turns") -> str:
        """Return parameterized SQL for PostgreSQL export jobs."""
        return (
            f"INSERT INTO {table_name} ("
            "session_id, role, content, tool_calls, sae_features, emotion_profile, "
            "thinking_text, deliberation_gate_interventions, action_gate_decisions, created_at"
            ") VALUES ("
            "%s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, %s::jsonb, %s::jsonb, %s"
            ");"
        )

    def _ensure_schema(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS transcript_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_calls TEXT NOT NULL DEFAULT '[]',
                    sae_features TEXT NOT NULL DEFAULT '{}',
                    emotion_profile TEXT,
                    thinking_text TEXT,
                    deliberation_gate_interventions TEXT NOT NULL DEFAULT '[]',
                    action_gate_decisions TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transcript_turns_session_time
                ON transcript_turns (session_id, created_at)
                """
            )
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _json_dump(value: Any) -> str:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _json_load(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return default

    @staticmethod
    def _normalize_sae_features(features: Dict[int, float]) -> Dict[int, float]:
        normalized: Dict[int, float] = {}
        for key, value in features.items():
            normalized[int(key)] = float(value)
        return normalized

    @staticmethod
    def _normalize_emotion_profile(emotion_profile: Any) -> Optional[Dict[str, Any]]:
        if emotion_profile is None:
            return None
        if isinstance(emotion_profile, EmotionProfile):
            return emotion_profile.to_dict()
        if is_dataclass(emotion_profile):
            return dict(asdict(emotion_profile))
        if isinstance(emotion_profile, dict):
            return dict(emotion_profile)
        raise TypeError("emotion_profile must be EmotionProfile, dataclass, dict, or None")

    @staticmethod
    def _extract_gate_events(tool_calls: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        deliberation_events: List[Dict[str, Any]] = []
        action_gate_events: List[Dict[str, Any]] = []
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            raw_deliberation = call.get("deliberation_gate_interventions") or call.get("deliberation_gate_intervention")
            raw_action = call.get("action_gate_decisions") or call.get("action_gate_decision")
            for event in TranscriptLogger._listify(raw_deliberation):
                deliberation_events.append(event)
            for event in TranscriptLogger._listify(raw_action):
                action_gate_events.append(event)

            result_payload = call.get("result")
            if isinstance(result_payload, dict):
                for event in TranscriptLogger._listify(
                    result_payload.get("deliberation_gate_interventions")
                    or result_payload.get("deliberation_gate_intervention")
                ):
                    deliberation_events.append(event)
                for event in TranscriptLogger._listify(
                    result_payload.get("action_gate_decisions") or result_payload.get("action_gate_decision")
                ):
                    action_gate_events.append(event)
        return deliberation_events, action_gate_events

    @staticmethod
    def _listify(value: Any) -> Iterable[Dict[str, Any]]:
        if value is None:
            return []
        if isinstance(value, dict):
            return [dict(value)]
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _decode_sae_features(payload: Dict[str, Any]) -> Dict[int, float]:
        normalized: Dict[int, float] = {}
        for key, value in dict(payload).items():
            normalized[int(key)] = float(value)
        return normalized

    @staticmethod
    def _decode_emotion_profile(emotion_raw: Any) -> Optional[EmotionProfile]:
        parsed = TranscriptLogger._json_load(emotion_raw, default=None)
        if parsed is None:
            return None
        if not isinstance(parsed, dict):
            return None
        return EmotionProfile(
            valence=float(parsed.get("valence", 0.0)),
            arousal=float(parsed.get("arousal", 0.0)),
            stress=float(parsed.get("stress", 0.0)),
            confidence=float(parsed.get("confidence", 0.0)),
            labels=[str(item) for item in parsed.get("labels", [])],
        )

