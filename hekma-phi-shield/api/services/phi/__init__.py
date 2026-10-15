"""PHI detection package (OpenAI now; local model later)."""

from api.services.phi.factory import PhiDetectorFactory
from api.services.phi.service import PhiDetectionService
from api.services.phi.types import PHI_ENTITY_TYPE_NAMES, PHI_LABELS

__all__ = [
    "PhiDetectorFactory",
    "PhiDetectionService",
    "PHI_ENTITY_TYPE_NAMES",
    "PHI_LABELS",
]
