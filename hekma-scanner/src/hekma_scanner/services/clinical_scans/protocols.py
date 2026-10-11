from typing import Any, Dict, List, Optional, Protocol

from .modules import ClinicalModule


class ClinicalModuleStrategy(Protocol):
    """Per-module OCR + persist strategy (Strategy pattern)."""

    module: ClinicalModule

    def extraction_profile(self) -> Dict[str, Any]:
        """Return system_prompt, user_prompt, json_schema, invalid_error_code."""
        ...

    def map_records(self, extracted: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Map AI JSON → DB insert payloads."""
        ...

    def persist_record(self, patient_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Insert one record into the module's MySQL table."""
        ...

    def matching_record(self, patient_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find the persisted clinical row this OCR payload maps to, if any."""
        ...

    def enrich_scan_payload(self, payload: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
        ...
