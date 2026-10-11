"""Load clinical scan document limits from JSON (PDF pages, file size)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DEFAULT_CONFIG_PATH = Path(__file__).with_name("clinical_scan_config.json")
CONFIG_PATH_ENV = "CLINICAL_SCAN_CONFIG_PATH"


@dataclass(frozen=True)
class ClinicalScanConfig:
    """Validated limits for clinical document uploads."""

    max_pdf_pages: int
    max_file_size_mb: int

    @property
    def max_file_size_bytes(self) -> int:
        """File size ceiling in bytes."""
        return self.max_file_size_mb * 1024 * 1024

    @classmethod
    def load(cls, path: Path) -> "ClinicalScanConfig":
        """Load JSON config; fail fast on missing/invalid values."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError(f"Clinical scan config not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Clinical scan config is invalid JSON: {path}") from exc

        max_pdf_pages = payload.get("maxPdfPages", 5)
        max_file_size_mb = payload.get("maxFileSizeMb", 10)
        try:
            max_pdf_pages = int(max_pdf_pages)
            max_file_size_mb = int(max_file_size_mb)
        except (TypeError, ValueError) as exc:
            raise ValueError("maxPdfPages and maxFileSizeMb must be integers") from exc

        if max_pdf_pages < 1 or max_pdf_pages > 50:
            raise ValueError("maxPdfPages must be between 1 and 50")
        if max_file_size_mb < 1 or max_file_size_mb > 100:
            raise ValueError("maxFileSizeMb must be between 1 and 100")

        return cls(max_pdf_pages=max_pdf_pages, max_file_size_mb=max_file_size_mb)


def _resolve_config_path() -> Path:
    """Prefer CLINICAL_SCAN_CONFIG_PATH when set."""
    override = (os.getenv(CONFIG_PATH_ENV) or "").strip()
    return Path(override) if override else DEFAULT_CONFIG_PATH


@lru_cache(maxsize=1)
def get_clinical_scan_config() -> ClinicalScanConfig:
    """Cached clinical scan limits from clinical_scan_config.json."""
    return ClinicalScanConfig.load(_resolve_config_path())
