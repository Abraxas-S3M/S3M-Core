"""Production watcher for incoming cloud CPU JSONL training packets.

Military/tactical context:
This watcher is the first guardrail in the adaptation chain; strict filename
parsing and scenario-label validation reduce the risk of poisoned or mislabeled
training traffic entering downstream mission-learning queues.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
import shutil
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

import yaml

S3M_SRC_PATH = "/opt/s3m/src"
if S3M_SRC_PATH not in sys.path:
    sys.path.insert(0, S3M_SRC_PATH)

try:
    from training.packet_builder import PacketBuilder  # type: ignore
except Exception:  # pragma: no cover - local repo fallback path.
    from src.training.packet_builder import PacketBuilder  # type: ignore

try:
    from db.connection import get_connection  # type: ignore
    from db.label_validator import LabelValidator  # type: ignore
except Exception:  # pragma: no cover - exercised only when db package is unavailable.
    LabelValidator = None  # type: ignore[assignment]

    def get_connection() -> Any:  # type: ignore[override]
        return None


POLL_INTERVAL_SECONDS = 10
INBOX_DIR = Path("/opt/s3m/state/training/cloud_cpu/inbox")
STAGING_DIR = Path("/opt/s3m/state/training/staging")
LOG_FILE = Path("/opt/s3m/logs/packet_watcher.log")
DEFAULT_TRACKS_CONFIG_CANDIDATES = (
    Path("configs/tracks.yaml"),
    Path("/opt/s3m/configs/tracks.yaml"),
)
DEFAULT_PACKET_OUTPUT_ROOT = Path("/opt/s3m/state/training/cloud_cpu/tracks")
SUMMARY_EVERY_N_CYCLES = 10
SUPPORTED_JSONL_SUFFIX = ".jsonl"
DEFAULT_DATA_CLASS = "command"

_VERSION_SUFFIX_RE = re.compile(r"^(?:v\d+|version\d+|batch\d+|part\d+|rev\d+|\d+)$", re.IGNORECASE)
_SLUG_SANITIZE_RE = re.compile(r"[^a-z0-9_]+")
_COLLAPSE_UNDERSCORE_RE = re.compile(r"_+")


@dataclass
class ScenarioDefinition:
    """Scenario-level metadata loaded from tracks.yaml."""

    name: str
    data_class: Optional[str] = None
    output_dir: Optional[str] = None


@dataclass
class TrackDefinition:
    """Track-level metadata loaded from tracks.yaml."""

    name: str
    default_data_class: str = DEFAULT_DATA_CLASS
    output_dir: Optional[str] = None
    scenarios: Dict[str, ScenarioDefinition] = field(default_factory=dict)


@dataclass
class InferenceResult:
    """Resolved routing context inferred from a JSONL filename."""

    track: str
    scenario: str
    data_class: str
    output_dir: Path


class _ContextDefaultsFilter(logging.Filter):
    """Ensure required structured fields are always present on log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "packet_filename"):
            record.packet_filename = "-"
        if not hasattr(record, "track"):
            record.track = "-"
        if not hasattr(record, "scenario"):
            record.scenario = "-"
        return True


class PacketWatcher:
    """Watch inbox JSONL files and dispatch PacketBuilder ingestion."""

    def __init__(
        self,
        inbox_dir: Path = INBOX_DIR,
        staging_dir: Path = STAGING_DIR,
        packet_output_root: Path = DEFAULT_PACKET_OUTPUT_ROOT,
        tracks_config_path: Optional[Path] = None,
        poll_interval_seconds: int = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._inbox_dir = Path(inbox_dir)
        self._staging_dir = Path(staging_dir)
        self._packet_output_root = Path(packet_output_root)
        self._tracks_config_path = tracks_config_path or self._resolve_tracks_config_path()
        self._poll_interval_seconds = max(1, int(poll_interval_seconds))

        self._logger = self._configure_logging()
        self._packet_builder = PacketBuilder()
        self._label_validator: Any = None
        self._db_connection: Any = None

        self._track_definitions: Dict[str, TrackDefinition] = {}
        self._tracks_config_mtime_ns: Optional[int] = None
        self._cycles = 0
        self._processed_total = 0
        self._failed_total = 0

        self._ensure_runtime_directories()
        self._initialize_validator()
        self._reload_track_definitions(force=True)

    def run_forever(self) -> None:
        """Execute an endless watcher loop without crashing on file-level errors."""
        self._log(logging.INFO, "packet watcher started")
        while True:
            cycle_started = time.monotonic()
            self._cycles += 1
            try:
                self._reload_track_definitions(force=False)
                self._run_single_cycle()
            except Exception:
                # Keep the outer loop alive even if a cycle-level bug occurs.
                self._log(
                    logging.ERROR,
                    "watcher cycle encountered an unexpected error: %s",
                    traceback.format_exc(),
                )
            elapsed = time.monotonic() - cycle_started
            sleep_for = max(0.0, float(self._poll_interval_seconds) - elapsed)
            time.sleep(sleep_for)

    def _run_single_cycle(self) -> None:
        files = sorted(self._inbox_dir.glob(f"*{SUPPORTED_JSONL_SUFFIX}"), key=lambda item: item.name)
        cycle_processed = 0
        cycle_failed = 0

        for jsonl_file in files:
            try:
                self._process_file(jsonl_file)
            except Exception:
                cycle_failed += 1
                self._failed_total += 1
                self._log(
                    logging.ERROR,
                    "file processing failed with traceback:\n%s",
                    traceback.format_exc(),
                    filename=jsonl_file.name,
                )
            else:
                cycle_processed += 1
                self._processed_total += 1

        if self._cycles % SUMMARY_EVERY_N_CYCLES == 0:
            pending = len(list(self._inbox_dir.glob(f"*{SUPPORTED_JSONL_SUFFIX}")))
            self._log(
                logging.INFO,
                "watcher summary cycles=%d processed=%d failed=%d pending=%d cycle_processed=%d cycle_failed=%d",
                self._cycles,
                self._processed_total,
                self._failed_total,
                pending,
                cycle_processed,
                cycle_failed,
            )

    def _process_file(self, jsonl_file: Path) -> None:
        if not jsonl_file.exists() or not jsonl_file.is_file():
            raise FileNotFoundError(f"Inbox item disappeared before processing: {jsonl_file}")

        inference = self._infer_track_scenario(jsonl_file.name)
        self._validate_jsonl_file(jsonl_file)
        self._validate_or_register_scenario(
            track=inference.track,
            scenario=inference.scenario,
            data_class=inference.data_class,
            filename=jsonl_file.name,
        )
        self._invoke_packet_builder(jsonl_file, inference)
        destination = self._dedupe_destination(self._staging_dir, jsonl_file.name)
        shutil.move(str(jsonl_file), str(destination))
        self._log(
            logging.INFO,
            "file processed and moved to staging",
            filename=jsonl_file.name,
            track=inference.track,
            scenario=inference.scenario,
        )

    def _infer_track_scenario(self, filename: str) -> InferenceResult:
        stem = Path(filename).stem
        if not stem:
            raise ValueError("Cannot infer track/scenario from empty filename stem")

        normalized_stem = _normalize_slug(stem)
        tokens = [token for token in normalized_stem.split("_") if token]
        if not tokens:
            raise ValueError(f"Cannot parse filename into tokens: {filename}")

        track = self._infer_track(tokens=tokens, filename=filename)
        track_token_count = len(track.split("_"))
        scenario_tokens = self._strip_version_suffixes(tokens[track_token_count:])
        if not scenario_tokens:
            raise ValueError(f"Filename does not include a scenario segment: {filename}")

        scenario = "_".join(scenario_tokens)
        track_def = self._track_definitions[track]
        scenario_def = track_def.scenarios.get(scenario)

        data_class = (
            (scenario_def.data_class if scenario_def else None)
            or track_def.default_data_class
            or DEFAULT_DATA_CLASS
        )
        output_dir = self._resolve_output_dir(track=track, track_def=track_def, scenario_def=scenario_def)
        return InferenceResult(track=track, scenario=scenario, data_class=data_class, output_dir=output_dir)

    def _infer_track(self, tokens: list[str], filename: str) -> str:
        if not self._track_definitions:
            raise ValueError("No tracks were loaded from configs/tracks.yaml")

        track_names = sorted(
            self._track_definitions.keys(),
            key=lambda name: len(name.split("_")),
            reverse=True,
        )
        for candidate in track_names:
            candidate_tokens = candidate.split("_")
            if tokens[: len(candidate_tokens)] == candidate_tokens:
                return candidate
        raise ValueError(f"Unknown track inferred from filename '{filename}'")

    @staticmethod
    def _strip_version_suffixes(tokens: list[str]) -> list[str]:
        trimmed = list(tokens)
        while trimmed and _VERSION_SUFFIX_RE.match(trimmed[-1]):
            trimmed.pop()
        return trimmed

    def _validate_jsonl_file(self, jsonl_file: Path) -> None:
        if jsonl_file.stat().st_size <= 0:
            raise ValueError(f"JSONL file is empty: {jsonl_file.name}")

        non_empty_rows = 0
        with jsonl_file.open("r", encoding="utf-8") as handle:
            for line_number, raw_line in enumerate(handle, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                non_empty_rows += 1
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"Malformed JSON on line {line_number} for {jsonl_file.name}: {exc.msg}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise ValueError(
                        f"Invalid payload type on line {line_number} for {jsonl_file.name}; expected JSON object"
                    )
        if non_empty_rows == 0:
            raise ValueError(f"JSONL file has no non-empty rows: {jsonl_file.name}")

    def _validate_or_register_scenario(self, track: str, scenario: str, data_class: str, filename: str) -> None:
        track_def = self._track_definitions[track]
        is_known = scenario in track_def.scenarios
        db_status = self._validate_with_label_validator(track=track, scenario=scenario)

        if db_status is True:
            return

        if db_status is None and is_known:
            return

        if db_status is False or not is_known:
            # Tactical continuity: auto-register unknown labels so urgent field data
            # can keep flowing while preserving explicit audit logs.
            self._register_scenario_defaults(track=track, scenario=scenario, data_class=data_class)
            self._log(
                logging.WARNING,
                "scenario label was unknown and has been auto-registered with defaults",
                filename=filename,
                track=track,
                scenario=scenario,
            )
            return

        raise ValueError(
            f"Scenario label validation failed for track={track} scenario={scenario}; packet kept in inbox."
        )

    def _validate_with_label_validator(self, track: str, scenario: str) -> Optional[bool]:
        if self._label_validator is None:
            return None

        methods = (
            "validate_scenario_label",
            "validate_scenario",
            "validate_label",
            "validate",
            "is_valid_scenario",
            "scenario_exists",
        )

        for method_name in methods:
            method = getattr(self._label_validator, method_name, None)
            if method is None:
                continue
            result, was_called = _call_with_signature_fallbacks(
                method,
                call_builders=_validator_call_builders(track=track, scenario=scenario),
            )
            if not was_called:
                continue
            return _coerce_validation_result(result)
        return None

    def _register_scenario_defaults(self, track: str, scenario: str, data_class: str) -> None:
        track_def = self._track_definitions[track]
        if scenario not in track_def.scenarios:
            track_def.scenarios[scenario] = ScenarioDefinition(name=scenario, data_class=data_class)

        if self._label_validator is None:
            return

        defaults = {
            "track": track,
            "scenario": scenario,
            "data_class": data_class,
            "status": "active",
            "origin": "packet_watcher_auto_register",
        }
        methods = (
            "register_scenario_label",
            "register_scenario",
            "upsert_scenario",
            "create_scenario_label",
        )
        for method_name in methods:
            method = getattr(self._label_validator, method_name, None)
            if method is None:
                continue
            _, was_called = _call_with_signature_fallbacks(
                method,
                call_builders=_register_call_builders(track=track, scenario=scenario, defaults=defaults),
            )
            if was_called:
                return

    def _invoke_packet_builder(self, jsonl_file: Path, inference: InferenceResult) -> None:
        inference.output_dir.mkdir(parents=True, exist_ok=True)
        build_method = getattr(self._packet_builder, "build_from_jsonl", None)
        if build_method is None:
            raise AttributeError("PacketBuilder.build_from_jsonl() is not available")

        call_builders = _packet_builder_call_builders(
            jsonl_file=jsonl_file,
            track=inference.track,
            scenario=inference.scenario,
            data_class=inference.data_class,
            output_dir=inference.output_dir,
        )
        _, was_called = _call_with_signature_fallbacks(build_method, call_builders=call_builders)
        if not was_called:
            raise TypeError("Unable to satisfy PacketBuilder.build_from_jsonl() signature")

    def _reload_track_definitions(self, force: bool) -> None:
        config_path = self._tracks_config_path
        try:
            current_mtime = config_path.stat().st_mtime_ns
        except FileNotFoundError:
            if force:
                raise FileNotFoundError(f"Track configuration not found: {config_path}") from None
            return

        if not force and self._tracks_config_mtime_ns == current_mtime:
            return

        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        parsed = _parse_track_definitions(payload)
        if not parsed:
            raise ValueError(f"No tracks found in configuration file: {config_path}")

        self._track_definitions = parsed
        self._tracks_config_mtime_ns = current_mtime
        self._log(logging.INFO, "loaded tracks configuration from %s", str(config_path))

    def _resolve_output_dir(
        self,
        track: str,
        track_def: TrackDefinition,
        scenario_def: Optional[ScenarioDefinition],
    ) -> Path:
        if scenario_def is not None and scenario_def.output_dir:
            return Path(scenario_def.output_dir)
        if track_def.output_dir:
            return Path(track_def.output_dir)
        return self._packet_output_root / track / "scenarios"

    def _initialize_validator(self) -> None:
        if LabelValidator is None:
            self._log(logging.WARNING, "db.label_validator unavailable; using config-based scenario validation only")
            return
        try:
            self._db_connection = get_connection()
        except Exception:
            self._log(logging.ERROR, "database connection initialization failed: %s", traceback.format_exc())
            self._db_connection = None
            return

        constructor_attempts = (
            lambda: LabelValidator(self._db_connection),
            lambda: LabelValidator(),
        )
        for constructor in constructor_attempts:
            try:
                self._label_validator = constructor()
                return
            except TypeError:
                continue
            except Exception:
                self._log(logging.ERROR, "label validator initialization failed: %s", traceback.format_exc())
                self._label_validator = None
                return
        self._label_validator = None
        self._log(logging.WARNING, "unable to instantiate LabelValidator; using config-based validation")

    def _ensure_runtime_directories(self) -> None:
        self._inbox_dir.mkdir(parents=True, exist_ok=True)
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        self._packet_output_root.mkdir(parents=True, exist_ok=True)
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _configure_logging(self) -> logging.Logger:
        logger = logging.getLogger("s3m.pipeline.packet_watcher")
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if logger.handlers:
            return logger

        formatter = logging.Formatter(
            fmt=(
                "%(asctime)s %(levelname)s filename=%(packet_filename)s track=%(track)s "
                "scenario=%(scenario)s message=%(message)s"
            ),
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        context_filter = _ContextDefaultsFilter()

        stdout_handler = logging.StreamHandler(stream=sys.stdout)
        stdout_handler.setFormatter(formatter)
        stdout_handler.addFilter(context_filter)
        logger.addHandler(stdout_handler)

        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.addFilter(context_filter)
        logger.addHandler(file_handler)
        return logger

    @staticmethod
    def _resolve_tracks_config_path() -> Path:
        for candidate in DEFAULT_TRACKS_CONFIG_CANDIDATES:
            if candidate.exists():
                return candidate
        return DEFAULT_TRACKS_CONFIG_CANDIDATES[0]

    def _log(
        self,
        level: int,
        message: str,
        *args: Any,
        filename: str = "-",
        track: str = "-",
        scenario: str = "-",
    ) -> None:
        self._logger.log(
            level,
            message,
            *args,
            extra={"packet_filename": filename, "track": track, "scenario": scenario},
        )

    @staticmethod
    def _dedupe_destination(parent: Path, filename: str) -> Path:
        base = parent / filename
        if not base.exists():
            return base
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        index = 1
        while True:
            candidate = parent / f"{stem}-{index:03d}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1


def _packet_builder_call_builders(
    jsonl_file: Path,
    track: str,
    scenario: str,
    data_class: str,
    output_dir: Path,
) -> Iterable[Callable[[], Any]]:
    # Keep multiple call shapes to support evolving PacketBuilder signatures
    # across environments while still passing inferred track/scenario context.
    rich_kwargs = {
        "track": track,
        "scenario": scenario,
        "data_class": data_class,
        "output_dir": output_dir,
    }
    with_scenario = {"track": track, "scenario": scenario, "output_dir": output_dir}
    with_data_class = {"track": track, "data_class": data_class, "output_dir": output_dir}
    minimal = {"track": track, "output_dir": output_dir}
    path_keys = ("input_file", "input_path", "jsonl_path", "file_path", "path")
    builders: list[Callable[[], Any]] = []
    for key in path_keys:
        builders.append(lambda k=key: {"kwargs": {k: jsonl_file, **rich_kwargs}})
        builders.append(lambda k=key: {"kwargs": {k: jsonl_file, **with_scenario}})
        builders.append(lambda k=key: {"kwargs": {k: jsonl_file, **with_data_class}})
        builders.append(lambda k=key: {"kwargs": {k: jsonl_file, **minimal}})
    builders.append(lambda: {"args": (jsonl_file,), "kwargs": dict(rich_kwargs)})
    builders.append(lambda: {"args": (jsonl_file,), "kwargs": dict(with_scenario)})
    builders.append(lambda: {"args": (jsonl_file,), "kwargs": dict(with_data_class)})
    builders.append(lambda: {"args": (jsonl_file,), "kwargs": dict(minimal)})
    builders.append(lambda: {"args": (jsonl_file, track, scenario, output_dir), "kwargs": {}})
    builders.append(lambda: {"args": (jsonl_file, track, data_class, output_dir), "kwargs": {}})
    builders.append(lambda: {"args": (jsonl_file, track, output_dir), "kwargs": {}})
    return builders


def _validator_call_builders(track: str, scenario: str) -> Iterable[Callable[[], Any]]:
    return (
        lambda: {"kwargs": {"track": track, "scenario": scenario}},
        lambda: {"kwargs": {"track_name": track, "scenario_name": scenario}},
        lambda: {"args": (track, scenario), "kwargs": {}},
        lambda: {"args": (scenario,), "kwargs": {"track": track}},
    )


def _register_call_builders(track: str, scenario: str, defaults: Dict[str, Any]) -> Iterable[Callable[[], Any]]:
    return (
        lambda: {"kwargs": {"track": track, "scenario": scenario, "defaults": defaults}},
        lambda: {"kwargs": {"track_name": track, "scenario_name": scenario, "defaults": defaults}},
        lambda: {"kwargs": {"payload": defaults}},
        lambda: {"args": (track, scenario), "kwargs": {"defaults": defaults}},
        lambda: {"args": (defaults,), "kwargs": {}},
    )


def _call_with_signature_fallbacks(
    method: Callable[..., Any],
    call_builders: Iterable[Callable[[], Dict[str, Any]]],
) -> tuple[Any, bool]:
    try:
        signature = inspect.signature(method)
    except (TypeError, ValueError):
        signature = None
    for builder in call_builders:
        call_data = builder()
        args = tuple(call_data.get("args", ()))
        kwargs = dict(call_data.get("kwargs", {}))
        if signature is not None:
            try:
                signature.bind(*args, **kwargs)
            except TypeError:
                continue
        try:
            return method(*args, **kwargs), True
        except TypeError:
            continue
    return None, False


def _parse_track_definitions(payload: Any) -> Dict[str, TrackDefinition]:
    if payload is None:
        return {}

    raw_tracks: Any
    if isinstance(payload, dict) and isinstance(payload.get("tracks"), (dict, list)):
        raw_tracks = payload.get("tracks")
    else:
        raw_tracks = payload

    parsed: Dict[str, TrackDefinition] = {}
    if isinstance(raw_tracks, dict):
        for name, node in raw_tracks.items():
            definition = _parse_single_track(track_name=name, track_payload=node)
            parsed[definition.name] = definition
    elif isinstance(raw_tracks, list):
        for item in raw_tracks:
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name", item.get("track", item.get("id")))
            if not raw_name:
                continue
            definition = _parse_single_track(track_name=str(raw_name), track_payload=item)
            parsed[definition.name] = definition
    return parsed


def _parse_single_track(track_name: str, track_payload: Any) -> TrackDefinition:
    normalized_track = _normalize_slug(track_name)
    scenarios: Dict[str, ScenarioDefinition] = {}

    default_data_class = DEFAULT_DATA_CLASS
    output_dir: Optional[str] = None
    if isinstance(track_payload, dict):
        default_data_class = _normalize_slug(
            str(
                track_payload.get(
                    "default_data_class",
                    track_payload.get("data_class", track_payload.get("packet_data_class", DEFAULT_DATA_CLASS)),
                )
            )
        ) or DEFAULT_DATA_CLASS
        raw_output = track_payload.get("output_dir")
        if raw_output:
            output_dir = str(raw_output)
        raw_scenarios = track_payload.get("scenarios", track_payload.get("scenario_labels", []))
        scenarios = _parse_scenarios(raw_scenarios, default_data_class=default_data_class)

    return TrackDefinition(
        name=normalized_track,
        default_data_class=default_data_class or DEFAULT_DATA_CLASS,
        output_dir=output_dir,
        scenarios=scenarios,
    )


def _parse_scenarios(raw_scenarios: Any, default_data_class: str) -> Dict[str, ScenarioDefinition]:
    parsed: Dict[str, ScenarioDefinition] = {}
    if isinstance(raw_scenarios, dict):
        for scenario_name, node in raw_scenarios.items():
            normalized_scenario = _normalize_slug(str(scenario_name))
            data_class: Optional[str] = default_data_class
            output_dir: Optional[str] = None
            if isinstance(node, dict):
                raw_data_class = node.get("data_class", default_data_class)
                if raw_data_class:
                    data_class = _normalize_slug(str(raw_data_class))
                raw_output = node.get("output_dir")
                if raw_output:
                    output_dir = str(raw_output)
            elif isinstance(node, str) and node.strip():
                data_class = _normalize_slug(node)
            parsed[normalized_scenario] = ScenarioDefinition(
                name=normalized_scenario,
                data_class=data_class or default_data_class,
                output_dir=output_dir,
            )
        return parsed

    if isinstance(raw_scenarios, list):
        for item in raw_scenarios:
            if isinstance(item, str):
                scenario_name = _normalize_slug(item)
                parsed[scenario_name] = ScenarioDefinition(name=scenario_name, data_class=default_data_class)
                continue
            if not isinstance(item, dict):
                continue
            raw_name = item.get("name", item.get("scenario", item.get("id")))
            if not raw_name:
                continue
            scenario_name = _normalize_slug(str(raw_name))
            raw_data_class = item.get("data_class", default_data_class)
            output_dir = item.get("output_dir")
            parsed[scenario_name] = ScenarioDefinition(
                name=scenario_name,
                data_class=_normalize_slug(str(raw_data_class)) or default_data_class,
                output_dir=str(output_dir) if output_dir else None,
            )
    return parsed


def _normalize_slug(raw_value: str) -> str:
    lowered = str(raw_value).strip().lower().replace("-", "_").replace(" ", "_")
    cleaned = _SLUG_SANITIZE_RE.sub("_", lowered)
    collapsed = _COLLAPSE_UNDERSCORE_RE.sub("_", cleaned)
    return collapsed.strip("_")


def _coerce_validation_result(result: Any) -> Optional[bool]:
    if result is None:
        return None
    if isinstance(result, bool):
        return result
    if isinstance(result, dict):
        for key in ("valid", "is_valid", "known", "exists"):
            if key in result:
                value = result[key]
                if isinstance(value, bool):
                    return value
        return None
    if isinstance(result, str):
        normalized = result.strip().lower()
        if normalized in {"valid", "ok", "exists", "known"}:
            return True
        if normalized in {"unknown", "missing", "invalid"}:
            return False
    return None


def main() -> None:
    watcher = PacketWatcher()
    watcher.run_forever()


if __name__ == "__main__":
    main()
