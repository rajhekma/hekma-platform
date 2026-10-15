"""Build the configured PHI detector implementation."""

from __future__ import annotations

import logging

from api.config.settings import Settings
from api.services.phi.base import PhiDetector
from api.services.phi.disabled_detector import DisabledPhiDetector
from api.services.phi.local_detector import LocalPhiDetector
from api.services.phi.openai_detector import OpenAIPhiDetector

logger = logging.getLogger("phi-factory")


class PhiDetectorFactory:
    """Creates a PhiDetector from settings (openai | local)."""

    def create(self, settings: Settings) -> PhiDetector:
        """Instantiate the backend named by PHI_DETECTOR_BACKEND."""
        backend = (settings.PHI_DETECTOR_BACKEND or "openai").strip().lower()
        if backend == "local":
            logger.info("Using local PHI detector stub at %s", settings.PHI_LOCAL_MODEL_PATH)
            return LocalPhiDetector(model_path=settings.PHI_LOCAL_MODEL_PATH)

        if backend != "openai":
            return DisabledPhiDetector(
                detail=f"Unknown PHI_DETECTOR_BACKEND={backend!r}. Use 'openai' or 'local'."
            )

        api_key = (settings.OPENAI_API_KEY or "").strip()
        if not api_key:
            return DisabledPhiDetector(
                detail="PHI OpenAI backend selected but OPENAI_API_KEY is not set. "
                "Add it to .env (never commit the key)."
            )

        logger.info("Using OpenAI PHI detector model=%s", settings.OPENAI_PHI_MODEL)
        return OpenAIPhiDetector(
            api_key=api_key,
            model=settings.OPENAI_PHI_MODEL,
            timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
        )
