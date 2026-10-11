"""
Privacy Detection & Token Vault Service Client for Hekma Data Pipeline.
Integrates with privacy-detection-service (Diagram A Steps 2-6 and 8-9).
"""

import hashlib
import logging
import os
from typing import Any, Dict, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("privacy_client")


class PrivacyServiceClient:
    """High-performance HTTP client connecting to privacy-detection-service."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        api_key: Optional[str] = None,
        enabled: Optional[bool] = None,
    ):
        self.base_url = (base_url or os.getenv("PRIVACY_SERVICE_URL", "https://dev-pdsapi.hekma.ai")).rstrip("/")
        self.timeout = timeout or float(os.getenv("PRIVACY_SERVICE_TIMEOUT_SECONDS", "15.0"))
        self.api_key = api_key or os.getenv("PRIVACY_SERVICE_API_KEY", "hekma_sec_live_9a7b8c6d")
        
        env_enabled = os.getenv("PRIVACY_SERVICE_ENABLED", "true").lower() in ("true", "1", "yes")
        self.enabled = enabled if enabled is not None else env_enabled

        # Set up persistent HTTP connection pooling with retries
        self.session = requests.Session()
        retries = Retry(
            total=2,
            backoff_factor=0.2,
            status_forcelist=[502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=50, max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update({
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
        })

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
        }

    def is_healthy(self) -> bool:
        """Check if privacy service is online."""
        if not self.enabled:
            return False
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=3.0)
            return resp.status_code == 200
        except Exception as e:
            logger.warning("Privacy service health check failed: %s", e)
            return False

    def _sanitize_edge_cases(self, resource: Dict[str, Any], org_id: str = "default") -> Dict[str, Any]:
        """Client-side defense-in-depth: enforces Safe Harbor birthDate, emergency contact, and doctor masking."""
        if not isinstance(resource, dict):
            return resource

        rtype = resource.get("resourceType")

        # 1. Patient resource edge cases
        if rtype == "Patient":
            # Safe Harbor Birth Date (YYYY-01-01)
            bdate = resource.get("birthDate")
            if isinstance(bdate, str) and len(bdate.strip()) >= 4 and bdate[:4].isdigit():
                resource["birthDate"] = f"{bdate[:4]}-01-01"

            # Emergency Contacts (contact[])
            for c in resource.get("contact", []):
                if isinstance(c, dict):
                    c_name = c.get("name")
                    if isinstance(c_name, dict):
                        fam = c_name.get("family")
                        if isinstance(fam, str) and fam.strip() and not fam.startswith("FAM_"):
                            h = hashlib.sha256(f"{org_id}:{fam}".encode()).hexdigest()[:8]
                            c_name["family"] = f"FAM_{h}"
                        given = c_name.get("given")
                        if isinstance(given, list):
                            new_given = []
                            for g in given:
                                if isinstance(g, str) and g.strip() and not g.startswith("GIVEN_"):
                                    h = hashlib.sha256(f"{org_id}:{g}".encode()).hexdigest()[:8]
                                    new_given.append(f"GIVEN_{h}")
                                else:
                                    new_given.append(g)
                            c_name["given"] = new_given

                    for tc in c.get("telecom", []):
                        if isinstance(tc, dict):
                            v = tc.get("value")
                            if isinstance(v, str) and v.strip() and not v.startswith("PHONE_") and not v.startswith("EMAIL_"):
                                h = hashlib.sha256(f"{org_id}:{v}".encode()).hexdigest()[:8]
                                prefix = "EMAIL" if "email" in str(tc.get("system", "")).lower() else "PHONE"
                                tc["value"] = f"{prefix}_{h}"

        # 2. Observation / Encounter doctor display edge cases
        for perf in resource.get("performer", []):
            if isinstance(perf, dict):
                disp = perf.get("display")
                if isinstance(disp, str) and disp.strip() and not disp.startswith("[PERSON_"):
                    h = hashlib.sha256(f"{org_id}:{disp}".encode()).hexdigest()[:8]
                    perf["display"] = f"[PERSON_{h}]"

        return resource

    def anonymize_fhir_resource(self, resource: Dict[str, Any], org_id: str = "default") -> Dict[str, Any]:
        """
        Anonymizes a single FHIR resource (Patient, Condition, Observation, etc.)
        Preserves all clinical codes (LOINC, SNOMED, ICD-10, RxNorm).
        """
        if not self.enabled or not resource:
            return resource

        if not isinstance(resource, dict):
            return resource

        res_id = resource.get("id", "unknown")
        try:
            url = f"{self.base_url}/api/v1/anonymize/fhir"
            payload = {"resource": resource, "org_id": str(org_id or "default")}
            resp = self.session.post(url, json=payload, headers=self._headers(), timeout=self.timeout)

            if resp.status_code == 200:
                data = resp.json()
                return self._sanitize_edge_cases(data.get("anonymized_resource", resource), org_id=org_id)
            else:
                logger.warning(
                    "Privacy service returned status %d for FHIR resource %s: %s",
                    resp.status_code,
                    res_id,
                    resp.text[:200],
                )
                return resource
        except Exception as e:
            logger.error("Failed to anonymize FHIR resource (%s): %s. Falling back to original.", res_id, e)
            return resource

    def anonymize_fhir_batch(self, resources: List[Dict[str, Any]], org_id: str = "default") -> List[Dict[str, Any]]:
        """
        Batch-anonymizes multiple FHIR resources in a single HTTP request for high throughput.
        """
        if not self.enabled or not resources:
            return resources or []

        if not isinstance(resources, list):
            return resources

        try:
            url = f"{self.base_url}/api/v1/anonymize/fhir/batch"
            payload = {"resources": resources, "org_id": str(org_id or "default")}
            resp = self.session.post(url, json=payload, headers=self._headers(), timeout=self.timeout * 2)

            if resp.status_code == 200:
                data = resp.json()
                return [self._sanitize_edge_cases(r, org_id=org_id) for r in data.get("anonymized_resources", resources)]
            else:
                logger.warning("Batch FHIR anonymize returned %d: %s. Falling back to sequential.", resp.status_code, resp.text[:200])
                return [self.anonymize_fhir_resource(r, org_id=org_id) for r in resources]
        except Exception as e:
            logger.error("Failed to batch-anonymize FHIR resources: %s. Falling back to original.", e)
            return resources

    def anonymize_text(self, text: str, org_id: str = "default") -> str:
        """
        Anonymizes free-text clinical notes, impression text, and doctor narratives.
        """
        if not self.enabled or text is None:
            return text

        if not isinstance(text, str):
            return text

        if not text.strip():
            return text

        try:
            url = f"{self.base_url}/anonymize"
            payload = {"text": text, "org_id": str(org_id or "default")}
            resp = self.session.post(url, json=payload, headers=self._headers(), timeout=self.timeout)

            if resp.status_code == 200:
                data = resp.json()
                return data.get("anonymized_text", text)
            else:
                logger.warning("Privacy service returned status %d for text: %s", resp.status_code, resp.text[:200])
                return text
        except Exception as e:
            logger.error("Failed to anonymize text: %s. Falling back to original.", e)
            return text

    def anonymize_json(self, data: Any, org_id: str = "default") -> Any:
        """
        Anonymizes arbitrary nested JSON clinical payload.
        """
        if not self.enabled or not data:
            return data

        try:
            url = f"{self.base_url}/api/v1/anonymize/json"
            payload = {"resource": data, "org_id": str(org_id or "default")}
            resp = self.session.post(url, json=payload, headers=self._headers(), timeout=self.timeout)

            if resp.status_code == 200:
                res = resp.json()
                return res.get("anonymized_resource", data)
            else:
                return data
        except Exception as e:
            logger.error("Failed to anonymize JSON: %s. Falling back to original.", e)
            return data

    def restore_text(self, text: str, purpose: str = "patient_care", org_id: str = "default") -> str:
        """
        Restores tokens inside text for authorized clinical display (Diagram A Steps 8-9).
        Uses /restore endpoint with fallback to /internal/restore-text.
        """
        if not self.enabled or text is None:
            return text

        if not isinstance(text, str) or not text.strip():
            return text

        # 1. Try unified /restore endpoint
        try:
            url = f"{self.base_url}/restore"
            payload = {"text": text, "org_id": str(org_id or "default"), "purpose": purpose}
            resp = self.session.post(url, json=payload, headers=self._headers(), timeout=self.timeout)

            if resp.status_code == 200:
                data = resp.json()
                return data.get("restored_text", text)
        except Exception as e:
            logger.debug("Primary /restore failed (%s), trying fallback /internal/restore-text", e)

        # 2. Fallback to /internal/restore-text
        try:
            url = f"{self.base_url}/internal/restore-text"
            payload = {
                "text": text,
                "org_id": str(org_id or "default"),
                "purpose": purpose,
                "requester_id": "clinical_pipeline",
                "ip_address": "127.0.0.1",
            }
            resp = self.session.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("restored_text", text)
            else:
                logger.warning("Restore text failed with status %d: %s", resp.status_code, resp.text[:200])
                return text
        except Exception as e:
            logger.error("Failed to restore text: %s", e)
            return text

    def restore_json(self, data: Any, purpose: str = "patient_care", org_id: str = "default") -> Any:
        """
        Restores tokens inside nested JSON structures for authorized clinical display.
        """
        if not self.enabled or not data:
            return data

        try:
            url = f"{self.base_url}/internal/restore-json"
            payload = {
                "data": data,
                "org_id": str(org_id or "default"),
                "purpose": purpose,
            }
            resp = self.session.post(url, json=payload, headers=self._headers(), timeout=self.timeout)

            if resp.status_code == 200:
                res = resp.json()
                return res.get("restored_data", data)
            else:
                logger.warning("Restore JSON returned status %d: %s", resp.status_code, resp.text[:200])
                return data
        except Exception as e:
            logger.error("Failed to restore JSON: %s", e)
            return data


# Global singleton instance
privacy_client = PrivacyServiceClient()
