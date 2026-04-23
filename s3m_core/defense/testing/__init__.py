"""Adversarial resilience testing primitives for S3M defense layers.

Military/tactical context:
These utilities continuously verify that layered controls still protect
mission systems against credential theft, containment bypass, and tampering.
"""

from .canary_deployer import Canary, CanaryDeployer, CanaryTrip
from .defense_validator import DefenseValidator, LayerValidation, ValidationReport
from .regression_tester import DefenseRegressionTester, RegressionReport

__all__ = [
    "Canary",
    "CanaryDeployer",
    "CanaryTrip",
    "DefenseRegressionTester",
    "DefenseValidator",
    "LayerValidation",
    "RegressionReport",
    "ValidationReport",
]
