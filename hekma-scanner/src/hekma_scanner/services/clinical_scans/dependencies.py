"""FastAPI dependency providers — clinical scan services.

All providers use lru_cache for singleton-per-process instantiation,
mirroring the medications module pattern.
"""
from functools import lru_cache

from .smart_scan_service import SmartClinicalScanService


# ── Scan services ─────────────────────────────────────────────────────────────

@lru_cache
def get_smart_scan_service() -> SmartClinicalScanService:
    return SmartClinicalScanService()
