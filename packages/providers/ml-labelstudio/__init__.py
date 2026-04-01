"""Label Studio provider integration for S3M labeling workflows."""

from .adapter import LabelStudioAdapter
from .config import LabelStudioConfig, PROJECT_TEMPLATES

__all__ = ["LabelStudioAdapter", "LabelStudioConfig", "PROJECT_TEMPLATES"]
