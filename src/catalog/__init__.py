"""Dataset catalog and routing interfaces for offline training ingestion.

Military/tactical context:
Catalog and routing controls constrain which core datasets can influence a
scenario packet, reducing accidental data bleed across mission domains.
"""

from .dataset_catalog import (
    CatalogValidationResult,
    DatasetRecord,
    load_dataset_records,
    load_saudi_mod_scenario_domains,
    validate_catalog,
)
from .dataset_router import DatasetRoute, DatasetRouter

__all__ = [
    "CatalogValidationResult",
    "DatasetRecord",
    "DatasetRoute",
    "DatasetRouter",
    "load_dataset_records",
    "load_saudi_mod_scenario_domains",
    "validate_catalog",
]
