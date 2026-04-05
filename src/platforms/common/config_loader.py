"""YAML-driven HOOL configuration loader and runtime bootstrap.

This loader converts offline mission configuration into live tactical services:
platform adapters, ROE policy wiring, geofence controls, and operator authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import inspect
from pathlib import Path
from typing import Any

import yaml

from src.autonomy.engagement_logic import EngagementPipeline
from src.safety.control_authority import ControlAuthorityService, RangeComplianceEngine

from .messages import AuthorityLevel, ROEProfile
from .platform_registry import PlatformRegistry


DEFAULT_HOOL_CONFIG_DIR = Path("configs/hool")
DEFAULT_ADAPTER_CLASS_MAP: dict[str, str] = {
    "HMMWVAdapter": "src.platforms.ugv.hmmwv_adapter.HMMWVAdapter",
    "WarWarAdapter": "src.platforms.uav.warwar_adapter.WarWarAdapter",
    "G24Adapter": "src.platforms.usv.g24_adapter.G24Adapter",
    "HorizonAdapter": "src.platforms.fixed.horizon_adapter.HorizonAdapter",
}


@dataclass(frozen=True)
class HOOLConfigSet:
    """Typed container for all HOOL YAML payloads."""

    platforms: dict[str, Any]
    roe_profiles: dict[str, Any]
    geofences: dict[str, Any]
    missions: dict[str, Any]
    safety: dict[str, Any]


@dataclass(frozen=True)
class HOOLRuntimeContext:
    """Live HOOL runtime context produced by configuration bootstrap."""

    configs: HOOLConfigSet
    platform_registry: PlatformRegistry
    engagement_pipeline: EngagementPipeline
    range_compliance_engine: RangeComplianceEngine
    control_authority_service: ControlAuthorityService
    registered_operators: dict[str, AuthorityLevel]


def load_hool_configs(config_dir: str | Path = DEFAULT_HOOL_CONFIG_DIR) -> HOOLConfigSet:
    """Load all required HOOL YAML files from the local configuration folder."""
    root = Path(config_dir)
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"HOOL config directory does not exist: {root}")

    return HOOLConfigSet(
        platforms=_load_yaml_object(root / "platforms.yaml"),
        roe_profiles=_load_yaml_object(root / "roe_profiles.yaml"),
        geofences=_load_yaml_object(root / "geofences.yaml"),
        missions=_load_yaml_object(root / "missions.yaml"),
        safety=_load_yaml_object(root / "safety.yaml"),
    )


def bootstrap_hool_runtime(
    config_dir: str | Path = DEFAULT_HOOL_CONFIG_DIR,
    *,
    platform_registry: PlatformRegistry | None = None,
    engagement_pipeline: EngagementPipeline | None = None,
    range_compliance_engine: RangeComplianceEngine | None = None,
    control_authority_service: ControlAuthorityService | None = None,
    adapter_class_map: dict[str, str] | None = None,
) -> HOOLRuntimeContext:
    """Bootstrap HOOL runtime services from YAML configuration."""
    configs = load_hool_configs(config_dir=config_dir)

    registry = platform_registry or PlatformRegistry()
    pipeline = engagement_pipeline or EngagementPipeline()
    range_engine = range_compliance_engine or RangeComplianceEngine()
    authority = control_authority_service or ControlAuthorityService()
    class_map = dict(DEFAULT_ADAPTER_CLASS_MAP)
    if adapter_class_map:
        class_map.update(adapter_class_map)

    _configure_platforms(
        registry=registry,
        platforms_config=configs.platforms,
        adapter_class_map=class_map,
    )
    _configure_roe_profiles(pipeline=pipeline, roe_config=configs.roe_profiles)
    _configure_geofences(range_engine=range_engine, geofence_config=configs.geofences)
    operators = _configure_operator_defaults(authority=authority, safety_config=configs.safety)

    return HOOLRuntimeContext(
        configs=configs,
        platform_registry=registry,
        engagement_pipeline=pipeline,
        range_compliance_engine=range_engine,
        control_authority_service=authority,
        registered_operators=operators,
    )


def _load_yaml_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"required HOOL config is missing: {path}")
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"expected top-level mapping in {path}")
    return loaded


def _configure_platforms(
    *,
    registry: PlatformRegistry,
    platforms_config: dict[str, Any],
    adapter_class_map: dict[str, str],
) -> None:
    platforms = platforms_config.get("platforms")
    if not isinstance(platforms, list):
        raise ValueError("platforms.yaml must contain a 'platforms' list")

    for index, item in enumerate(platforms):
        if not isinstance(item, dict):
            raise ValueError(f"platforms[{index}] must be a mapping")
        platform_id = _required_non_empty_str(item, "platform_id", index=index)
        platform_type = _required_non_empty_str(item, "type", index=index)
        adapter_ref = _required_non_empty_str(item, "adapter_class", index=index)
        initial_position = _coerce_position(item.get("initial_position"), index=index)

        adapter_cls = _resolve_adapter_class(adapter_ref, adapter_class_map)
        adapter = _instantiate_adapter(
            adapter_cls=adapter_cls,
            platform_id=platform_id,
            initial_position=initial_position,
        )
        registry.register_adapter(
            platform_id=platform_id,
            platform_type=platform_type,
            adapter_class=adapter_ref,
            adapter=adapter,
            initial_position=initial_position,
        )


def _configure_roe_profiles(*, pipeline: EngagementPipeline, roe_config: dict[str, Any]) -> None:
    profiles_node = roe_config.get("roe_profiles")
    if not isinstance(profiles_node, dict):
        raise ValueError("roe_profiles.yaml must contain a 'roe_profiles' mapping")

    default_profile = _parse_roe_profile(profiles_node.get("default", ROEProfile.WEAPONS_TIGHT.value))
    zones_node = profiles_node.get("zones", {})
    if not isinstance(zones_node, dict):
        raise ValueError("roe_profiles.zones must be a mapping")
    zone_profiles = {str(zone_id): _parse_roe_profile(value) for zone_id, value in zones_node.items()}

    if hasattr(pipeline, "configure_zone_roe_profiles"):
        pipeline.configure_zone_roe_profiles(default_profile=default_profile, zone_profiles=zone_profiles)
    else:
        pipeline.roe_profile = default_profile
        setattr(pipeline, "zone_roe_profiles", zone_profiles)


def _configure_geofences(*, range_engine: RangeComplianceEngine, geofence_config: dict[str, Any]) -> None:
    geofences = geofence_config.get("geofences")
    if not isinstance(geofences, list):
        raise ValueError("geofences.yaml must contain a 'geofences' list")

    for index, item in enumerate(geofences):
        if not isinstance(item, dict):
            raise ValueError(f"geofences[{index}] must be a mapping")
        geofence_id = _required_non_empty_str(item, "geofence_id", index=index)
        policy = _required_non_empty_str(item, "policy", index=index).lower()
        polygon_raw = item.get("polygon_xy")
        polygon = _coerce_polygon_xy(polygon_raw, index=index)
        range_engine.add_geofence(geofence_id=geofence_id, polygon_xy=polygon, policy=policy)


def _configure_operator_defaults(
    *,
    authority: ControlAuthorityService,
    safety_config: dict[str, Any],
) -> dict[str, AuthorityLevel]:
    safety = safety_config.get("safety")
    if not isinstance(safety, dict):
        raise ValueError("safety.yaml must contain a 'safety' mapping")
    operators_node = safety.get("operators", [])
    if not isinstance(operators_node, list):
        raise ValueError("safety.operators must be a list")

    registered: dict[str, AuthorityLevel] = {}
    for index, item in enumerate(operators_node):
        if not isinstance(item, dict):
            raise ValueError(f"safety.operators[{index}] must be a mapping")
        operator_id = _required_non_empty_str(item, "operator_id", index=index)
        authority_level = _parse_authority_level(item.get("authority_level", AuthorityLevel.OPERATOR.value))
        authority.register_operator(operator_id, authority_level)
        registered[operator_id] = authority_level
    return registered


def _resolve_adapter_class(adapter_ref: str, adapter_class_map: dict[str, str]) -> type[Any]:
    import_path = adapter_class_map.get(adapter_ref, adapter_ref)
    if "." not in import_path:
        raise ValueError(
            f"adapter class '{adapter_ref}' must be in '<module>.<ClassName>' format or mapped alias"
        )
    module_name, class_name = import_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    adapter_cls = getattr(module, class_name, None)
    if adapter_cls is None or not inspect.isclass(adapter_cls):
        raise ValueError(f"adapter class not found: {import_path}")
    return adapter_cls


def _instantiate_adapter(
    *,
    adapter_cls: type[Any],
    platform_id: str,
    initial_position: tuple[float, float, float],
) -> Any:
    try:
        adapter = adapter_cls(platform_id=platform_id)
    except TypeError:
        adapter = adapter_cls(platform_id)

    if hasattr(adapter, "set_initial_position"):
        adapter.set_initial_position(initial_position)
    elif hasattr(adapter, "_position"):
        setattr(adapter, "_position", initial_position)
    elif hasattr(adapter, "position"):
        setattr(adapter, "position", initial_position)

    if hasattr(adapter, "connect"):
        adapter.connect()
    return adapter


def _required_non_empty_str(node: dict[str, Any], key: str, *, index: int) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"entry[{index}] missing valid '{key}'")
    return value.strip()


def _coerce_position(value: Any, *, index: int) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"entry[{index}] initial_position must be a 3-item list")
    return (float(value[0]), float(value[1]), float(value[2]))


def _coerce_polygon_xy(value: Any, *, index: int) -> list[tuple[float, float]]:
    if not isinstance(value, list) or len(value) < 3:
        raise ValueError(f"geofences[{index}] polygon_xy must have at least 3 points")
    polygon: list[tuple[float, float]] = []
    for vertex in value:
        if not isinstance(vertex, (list, tuple)) or len(vertex) != 2:
            raise ValueError(f"geofences[{index}] has invalid vertex: {vertex}")
        polygon.append((float(vertex[0]), float(vertex[1])))
    return polygon


def _parse_roe_profile(value: Any) -> ROEProfile:
    raw = str(value).strip().lower()
    try:
        return ROEProfile(raw)
    except Exception as exc:
        raise ValueError(f"unknown ROE profile: {value}") from exc


def _parse_authority_level(value: Any) -> AuthorityLevel:
    raw = str(value).strip().lower()
    try:
        return AuthorityLevel(raw)
    except Exception as exc:
        raise ValueError(f"unknown authority_level: {value}") from exc
