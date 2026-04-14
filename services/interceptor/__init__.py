"""Interceptor guidance services and data models.

Military context:
Exports tactical geometry computations used by the guidance computer to
maintain continuous pursuit-state awareness.
"""

from services.interceptor.geometry import InterceptGeometryComputer
from services.interceptor.models import InterceptGeometry

__all__ = [
    "InterceptGeometry",
    "InterceptGeometryComputer",
]
