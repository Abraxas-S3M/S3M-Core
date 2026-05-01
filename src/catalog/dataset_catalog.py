"""Dataset catalog loading and validation for routed training slices.

Military/tactical context:
Catalog validation is a pre-routing control that blocks malformed metadata from
injecting unauthorized datasets into command-track adaptation workflows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

DEFAULT_ONTOLOGY_PATH = Path("training/scenario_ontology/saudi_mod/v1/scenario_domains.json")
DEFAULT_ARTIFACT_ROOMS_PATH = Path("artifacts/rooms/room_registry.json")

REQUIRED_FIELDS = (
    "dataset_id",
    "name",
    "description",
    "r2_prefix",
    "formats",
    "source",
    "provenance",
    "geography",
    "language",
    "temporal_coverage",
    "operational_domains",
    "supported_scenario_domains",
    "supported_training_tracks",
    "supported_packet_types",
    "parser_status",
    "embedding_status",
    "data_sensitivity",
    "source_reliability",
    "update_frequency",
    "artifact_outputs_supported",
    "target_artifact_rooms",
    "routing_priority",
    "enabled",
)
OPTIONAL_FIELDS = ("r2_keys",)
ALL_FIELDS = set(REQUIRED_FIELDS).union(OPTIONAL_FIELDS)


@dataclass(frozen=True)
class DatasetRecord:
    """Normalized dataset catalog row."""

    dataset_id: str
    name: str
    description: str
    r2_prefix: str
    r2_keys: tuple[str, ...]
    formats: tuple[str, ...]
    source: str
    provenance: str
    geography: str
    language: str
    temporal_coverage: str
    operational_domains: tuple[str, ...]
    supported_scenario_domains: tuple[str, ...]
    supported_training_tracks: tuple[str, ...]
    supported_packet_types: tuple[str, ...]
    parser_status: str
    embedding_status: str
    data_sensitivity: str
    source_reliability: str
    update_frequency: str
    artifact_outputs_supported: tuple[str, ...]
    target_artifact_rooms: tuple[str, ...]
    routing_priority: int
    enabled: bool

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "DatasetRecord":
        return cls(
            dataset_id=_as_non_empty_string(raw["dataset_id"]),
            name=_as_non_empty_string(raw["name"]),
            description=_as_non_empty_string(raw["description"]),
            r2_prefix=_as_non_empty_string(raw["r2_prefix"]),
            r2_keys=tuple(_as_string_list(raw.get("r2_keys", []), field="r2_keys")),
            formats=tuple(_as_string_list(raw["formats"], field="formats")),
            source=_as_non_empty_string(raw["source"]),
            provenance=_as_non_empty_string(raw["provenance"]),
            geography=_as_non_empty_string(raw["geography"]),
            language=_as_non_empty_string(raw["language"]),
            temporal_coverage=_as_non_empty_string(raw["temporal_coverage"]),
            operational_domains=tuple(_as_string_list(raw["operational_domains"], field="operational_domains")),
            supported_scenario_domains=tuple(
                _as_string_list(raw["supported_scenario_domains"], field="supported_scenario_domains")
            ),
            supported_training_tracks=tuple(
                _as_string_list(raw["supported_training_tracks"], field="supported_training_tracks")
            ),
            supported_packet_types=tuple(
                _as_string_list(raw["supported_packet_types"], field="supported_packet_types")
            ),
            parser_status=_as_non_empty_string(raw["parser_status"]),
            embedding_status=_as_non_empty_string(raw["embedding_status"]),
            data_sensitivity=_as_non_empty_string(raw["data_sensitivity"]),
            source_reliability=_as_non_empty_string(raw["source_reliability"]),
            update_frequency=_as_non_empty_string(raw["update_frequency"]),
            artifact_outputs_supported=tuple(
                _as_string_list(raw["artifact_outputs_supported"], field="artifact_outputs_supported")
            ),
            target_artifact_rooms=tuple(
                _as_string_list(raw["target_artifact_rooms"], field="target_artifact_rooms")
            ),
            routing_priority=_as_routing_priority(raw["routing_priority"]),
            enabled=_as_bool(raw["enabled"], field="enabled"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Render as JSON-serializable dictionary for CLIs/tests."""
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "description": self.description,
            "r2_prefix": self.r2_prefix,
            "r2_keys": list(self.r2_keys),
            "formats": list(self.formats),
            "source": self.source,
            "provenance": self.provenance,
            "geography": self.geography,
            "language": self.language,
            "temporal_coverage": self.temporal_coverage,
            "operational_domains": list(self.operational_domains),
            "supported_scenario_domains": list(self.supported_scenario_domains),
            "supported_training_tracks": list(self.supported_training_tracks),
            "supported_packet_types": list(self.supported_packet_types),
            "parser_status": self.parser_status,
            "embedding_status": self.embedding_status,
            "data_sensitivity": self.data_sensitivity,
            "source_reliability": self.source_reliability,
            "update_frequency": self.update_frequency,
            "artifact_outputs_supported": list(self.artifact_outputs_supported),
            "target_artifact_rooms": list(self.target_artifact_rooms),
            "routing_priority": self.routing_priority,
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class CatalogValidationResult:
    """Validation results returned by validate_catalog."""

    catalog_path: Path
    records: tuple[DatasetRecord, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def total_records(self) -> int:
        return len(self.records)


def load_saudi_mod_scenario_domains(ontology_path: str | Path = DEFAULT_ONTOLOGY_PATH) -> set[str]:
    """Load canonical Saudi MOD v1 scenario domains (28 expected)."""
    payload = _load_json(Path(ontology_path))
    domains_raw = payload.get("scenario_domains", [])
    if not isinstance(domains_raw, list):
        raise ValueError("Ontology file must contain a list field named 'scenario_domains'.")
    domains = {_as_non_empty_string(value).strip().lower() for value in domains_raw}
    if len(domains) != 28:
        raise ValueError(f"Saudi MOD ontology must define exactly 28 domains; found {len(domains)}.")
    return domains


def load_valid_artifact_rooms(room_registry_path: str | Path = DEFAULT_ARTIFACT_ROOMS_PATH) -> set[str]:
    """Load allowed artifact room IDs used by GUI and validation pipelines."""
    payload = _load_json(Path(room_registry_path))
    rooms_raw = payload.get("rooms", [])
    if not isinstance(rooms_raw, list):
        raise ValueError("Artifact room registry must contain a list field named 'rooms'.")
    return {_as_non_empty_string(value).strip() for value in rooms_raw}


def load_dataset_records(catalog_path: str | Path) -> tuple[DatasetRecord, ...]:
    """Load dataset records without running cross-file validation checks."""
    records: list[DatasetRecord] = []
    for raw in _extract_dataset_rows(_load_json(Path(catalog_path))):
        records.append(DatasetRecord.from_mapping(_as_mapping(raw)))
    return tuple(records)


def validate_catalog(
    catalog_path: str | Path,
    *,
    ontology_path: str | Path = DEFAULT_ONTOLOGY_PATH,
    artifact_rooms_path: str | Path = DEFAULT_ARTIFACT_ROOMS_PATH,
) -> CatalogValidationResult:
    """Validate the dataset catalog schema and cross-file constraints."""
    catalog_file = Path(catalog_path)
    rows = _extract_dataset_rows(_load_json(catalog_file))
    valid_scenario_domains = load_saudi_mod_scenario_domains(ontology_path)
    valid_artifact_rooms = load_valid_artifact_rooms(artifact_rooms_path)

    errors: list[str] = []
    warnings: list[str] = []
    records: list[DatasetRecord] = []
    seen_dataset_ids: set[str] = set()

    for index, row in enumerate(rows):
        context = f"dataset[{index}]"
        if not isinstance(row, Mapping):
            errors.append(f"{context}: entry must be an object")
            continue

        missing = sorted(field for field in REQUIRED_FIELDS if field not in row)
        if missing:
            errors.append(f"{context}: missing required fields: {', '.join(missing)}")
            continue

        dataset_id = str(row.get("dataset_id", "")).strip()
        if not dataset_id:
            errors.append(f"{context}: dataset_id must be a non-empty string")
            continue
        context = f"dataset[{dataset_id}]"

        if dataset_id in seen_dataset_ids:
            errors.append(f"{context}: duplicate dataset_id")
            continue
        seen_dataset_ids.add(dataset_id)

        unknown_fields = sorted(key for key in row.keys() if key not in ALL_FIELDS)
        if unknown_fields:
            warnings.append(f"{context}: unknown fields ignored: {', '.join(unknown_fields)}")

        domain_errors = _validate_supported_domains(row, valid_scenario_domains, context)
        room_errors = _validate_artifact_rooms(row, valid_artifact_rooms, context)
        priority_errors = _validate_routing_priority(row, context)
        enabled_errors = _validate_enabled(row, context)

        errors.extend(domain_errors)
        errors.extend(room_errors)
        errors.extend(priority_errors)
        errors.extend(enabled_errors)

        if domain_errors or room_errors or priority_errors or enabled_errors:
            continue

        try:
            record = DatasetRecord.from_mapping(row)
        except (TypeError, ValueError) as exc:
            errors.append(f"{context}: invalid field type/value ({exc})")
            continue
        records.append(record)

    return CatalogValidationResult(
        catalog_path=catalog_file,
        records=tuple(records),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def _extract_dataset_rows(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        rows = payload.get("datasets", [])
        if isinstance(rows, list):
            return rows
    raise ValueError("Catalog JSON must be either a list or an object with a 'datasets' list.")


def _validate_supported_domains(
    row: Mapping[str, Any],
    valid_scenario_domains: set[str],
    context: str,
) -> list[str]:
    errors: list[str] = []
    try:
        provided = _as_string_list(row.get("supported_scenario_domains", []), field="supported_scenario_domains")
    except ValueError as exc:
        return [f"{context}: {exc}"]
    invalid = sorted({value for value in provided if value not in valid_scenario_domains})
    if invalid:
        errors.append(
            f"{context}: unsupported scenario domains: {', '.join(invalid)} "
            f"(valid count: {len(valid_scenario_domains)})"
        )
    return errors


def _validate_artifact_rooms(
    row: Mapping[str, Any],
    valid_artifact_rooms: set[str],
    context: str,
) -> list[str]:
    errors: list[str] = []
    try:
        provided = _as_string_list(row.get("target_artifact_rooms", []), field="target_artifact_rooms")
    except ValueError as exc:
        return [f"{context}: {exc}"]
    invalid = sorted({value for value in provided if value not in valid_artifact_rooms})
    if invalid:
        errors.append(f"{context}: unknown target_artifact_rooms: {', '.join(invalid)}")
    return errors


def _validate_routing_priority(row: Mapping[str, Any], context: str) -> list[str]:
    try:
        _as_routing_priority(row.get("routing_priority"))
    except ValueError as exc:
        return [f"{context}: {exc}"]
    return []


def _validate_enabled(row: Mapping[str, Any], context: str) -> list[str]:
    try:
        _as_bool(row.get("enabled"), field="enabled")
    except ValueError as exc:
        return [f"{context}: {exc}"]
    return []


def _as_bool(value: Any, *, field: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be boolean")


def _as_routing_priority(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("routing_priority must be integer between 1 and 100")
    if value < 1 or value > 100:
        raise ValueError("routing_priority out of range (1..100)")
    return value


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("catalog row must be an object")
    return value


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"JSON file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def _as_non_empty_string(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("must be a non-empty string")
    return normalized


def _as_string_list(value: Any, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(f"{field} must be a list of strings")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field} must contain only strings")
        text = item.strip()
        if not text:
            raise ValueError(f"{field} must not contain blank strings")
        normalized.append(text.lower())
    return _dedupe_preserve_order(normalized)


def _dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped
