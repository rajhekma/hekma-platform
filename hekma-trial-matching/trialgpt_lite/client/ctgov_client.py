"""
ClinicalTrials.gov REST API v2 Client.
Handles condition searches, field projection, pagination, exponential backoff, and query relaxation.
"""

import logging
import re
from typing import Any, Optional
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception,
    before_sleep_log,
)

from trialgpt_lite.config import (
    CTGOV_API_BASE_URL,
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    REQUEST_TIMEOUT_SECONDS,
    MAX_RETRIES,
    RETRY_BACKOFF_FACTOR,
)

logger = logging.getLogger("trialgpt_lite.ctgov_client")

# Key fields needed for matching, keeping payloads lightweight
PROJECTION_FIELDS = [
    "NCTId",
    "BriefTitle",
    "OfficialTitle",
    "OverallStatus",
    "Condition",
    "StudyType",
    "Phase",
    "DesignAllocation",
    "DesignInterventionModel",
    "DesignPrimaryPurpose",
    "DesignMasking",
    "EnrollmentCount",
    "EnrollmentType",
    "LeadSponsorName",
    "CollaboratorName",
    "InterventionType",
    "InterventionName",
    "InterventionDescription",
    "EligibilityCriteria",
    "Sex",
    "MinimumAge",
    "MaximumAge",
    "HealthyVolunteers",
    "BriefSummary",
    "StartDate",
    "StartDateType",
    "PrimaryCompletionDate",
    "CompletionDate",
    "StudyFirstPostDate",
    "LastUpdatePostDate",
    "PrimaryOutcomeMeasure",
    "PrimaryOutcomeTimeFrame",
    "PrimaryOutcomeDescription",
    "SecondaryOutcomeMeasure",
    "SecondaryOutcomeTimeFrame",
    "CentralContactName",
    "CentralContactRole",
    "CentralContactPhone",
    "CentralContactEMail",
    "OverallOfficialName",
    "OverallOfficialAffiliation",
    "OverallOfficialRole",
    "LocationFacility",
    "LocationCity",
    "LocationState",
    "LocationCountry",
]


def _is_retryable_exception(exc: BaseException) -> bool:
    """Retry on transient network errors or HTTP 429/5xx status codes."""
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        # 429: Too Many Requests, 5xx: Server errors
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return False


class ClinicalTrialsGovClient:
    """
    Robust HTTP client for ClinicalTrials.gov REST API v2.
    """

    def __init__(
        self,
        base_url: str = CTGOV_API_BASE_URL,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    @retry(
        retry=retry_if_exception(_is_retryable_exception),
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=RETRY_BACKOFF_FACTOR, min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _execute_get(self, endpoint: str, params: dict[str, Any]) -> dict[str, Any]:
        """Executes GET request with retries and error checking."""
        url = f"{self.base_url}{endpoint}"
        with httpx.Client(timeout=self.timeout) as client:
            headers = {"Accept": "application/json"}
            response = client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.json()

    def search_by_condition(
        self,
        condition: str,
        statuses: Optional[list[str]] = None,
        page_size: int = DEFAULT_PAGE_SIZE,
        page_token: Optional[str] = None,
        count_total: bool = True,
        use_fields_projection: bool = True,
        auto_relax_on_empty: bool = True,
        geo_filter: Optional[Any] = None,
    ) -> dict[str, Any]:
        """
        Searches studies by medical condition with optional 30-mile geo-radius proximity.

        Returns a dictionary containing:
            - "studies": list of raw study objects
            - "total_count": int (if count_total=True)
            - "next_page_token": Optional[str]
            - "query_used": str (the actual condition query used)
            - "relaxed": bool (whether query relaxation was applied)
        """
        clean_condition = condition.strip()
        if not clean_condition:
            return {
                "studies": [],
                "total_count": 0,
                "next_page_token": None,
                "query_used": "",
                "relaxed": False,
            }

        clamped_page_size = max(1, min(page_size, MAX_PAGE_SIZE))
        params: dict[str, Any] = {
            "query.cond": clean_condition,
            "pageSize": clamped_page_size,
        }

        if count_total:
            params["countTotal"] = "true"

        if statuses:
            params["filter.overallStatus"] = "|".join(statuses)

        if geo_filter:
            lat = getattr(geo_filter, "latitude", None) if not isinstance(geo_filter, dict) else geo_filter.get("latitude")
            lon = getattr(geo_filter, "longitude", None) if not isinstance(geo_filter, dict) else geo_filter.get("longitude")
            rad = getattr(geo_filter, "radius_miles", 30.0) if not isinstance(geo_filter, dict) else geo_filter.get("radius_miles", 30.0)
            city_or_zip = getattr(geo_filter, "city_or_zip", None) if not isinstance(geo_filter, dict) else geo_filter.get("city_or_zip")
            if lat is not None and lon is not None:
                params["filter.geo"] = f"distance({lat},{lon},{rad}mi)"
            elif city_or_zip:
                params["query.locn"] = str(city_or_zip).strip()

        if page_token:
            params["pageToken"] = page_token


        if use_fields_projection:
            params["fields"] = ",".join(PROJECTION_FIELDS)

        try:
            data = self._execute_get("/studies", params)
        except Exception as e:
            logger.error(f"Failed to query ClinicalTrials.gov for condition '{clean_condition}': {e}")
            raise

        studies = data.get("studies", [])
        total_count = data.get("totalCount", len(studies))
        next_page = data.get("nextPageToken")

        # Edge case: If 0 results returned and auto_relax_on_empty is True, attempt query relaxation
        if len(studies) == 0 and auto_relax_on_empty and not page_token:
            relaxed_query = self._relax_query(clean_condition)
            if relaxed_query and relaxed_query.lower() != clean_condition.lower():
                logger.info(f"Zero trials for '{clean_condition}'. Relaxing query to '{relaxed_query}'")
                params["query.cond"] = relaxed_query
                relaxed_data = self._execute_get("/studies", params)
                relaxed_studies = relaxed_data.get("studies", [])
                if relaxed_studies:
                    return {
                        "studies": relaxed_studies,
                        "total_count": relaxed_data.get("totalCount", len(relaxed_studies)),
                        "next_page_token": relaxed_data.get("nextPageToken"),
                        "query_used": relaxed_query,
                        "relaxed": True,
                    }

        return {
            "studies": studies,
            "total_count": total_count,
            "next_page_token": next_page,
            "query_used": clean_condition,
            "relaxed": False,
        }

    def fetch_study(self, nct_id: str) -> Optional[dict[str, Any]]:
        """Fetches full details for a single study by NCT ID."""
        clean_id = nct_id.strip().upper()
        if not clean_id.startswith("NCT"):
            raise ValueError(f"Invalid NCT ID format: {nct_id}")

        params = {"fields": ",".join(PROJECTION_FIELDS)}
        try:
            data = self._execute_get(f"/studies/{clean_id}", params)
            return data
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def get_recruiting_count(
        self,
        date_filter_field: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """
        Fetches the total count of studies with overallStatus=RECRUITING,
        optionally constrained by date range (e.g. StudyFirstPostDate or LastUpdatePostDate).
        """
        params: dict[str, Any] = {
            "filter.overallStatus": "RECRUITING",
            "countTotal": "true",
            "pageSize": 1,
        }

        if date_filter_field and start_date and end_date:
            params["filter.advanced"] = f"AREA[{date_filter_field}]RANGE[{start_date},{end_date}]"

        data = self._execute_get("/studies", params)
        return int(data.get("totalCount", 0))

    def get_study(self, nct_id: str) -> dict[str, Any]:
        """
        Fetches full study protocol by NCT ID from ClinicalTrials.gov API v2.
        """
        clean_nct = nct_id.strip().upper()
        return self._execute_get(f"/studies/{clean_nct}", {})

    def fetch_recruiting_feed(
        self,
        date_filter_field: str,
        start_date: str,
        end_date: str,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """
        Fetches a lightweight list of recruiting studies matching a specific date range.
        Used for displaying newly added or recently updated feeds.
        """
        feed_fields = [
            "NCTId",
            "BriefTitle",
            "OverallStatus",
            "StudyFirstPostDate",
            "LastUpdatePostDate",
            "Condition",
            "LeadSponsorName",
        ]
        params: dict[str, Any] = {
            "filter.overallStatus": "RECRUITING",
            "filter.advanced": f"AREA[{date_filter_field}]RANGE[{start_date},{end_date}]",
            "fields": ",".join(feed_fields),
            "pageSize": max(1, min(limit, 100)),
        }

        data = self._execute_get("/studies", params)
        raw_studies = data.get("studies", [])

        feed: list[dict[str, Any]] = []
        for s in raw_studies:
            proto = s.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status_mod = proto.get("statusModule", {})
            cond_mod = proto.get("conditionsModule", {})
            sponsor_mod = proto.get("sponsorCollaboratorsModule", {})

            nct_id = ident.get("nctId", "UNKNOWN")
            feed.append({
                "nct_id": nct_id,
                "title": ident.get("briefTitle", "Untitled Study"),
                "status": status_mod.get("overallStatus", "RECRUITING"),
                "first_posted": status_mod.get("studyFirstPostDateStruct", {}).get("date"),
                "last_updated": status_mod.get("lastUpdatePostDateStruct", {}).get("date"),
                "conditions": cond_mod.get("conditions", [])[:3],
                "lead_sponsor": sponsor_mod.get("leadSponsor", {}).get("name"),
                "web_url": f"https://clinicaltrials.gov/study/{nct_id}",
            })

        return feed

    @staticmethod
    def _relax_query(query: str) -> Optional[str]:
        """
        Strips common medical stage / severity qualifiers to broaden search
        if an overly specific query yields 0 results.
        """
        # Common qualifiers that might over-constrain the API search
        qualifiers = [
            r"\bstage\s+[ivx0-9]+\b",
            r"\bgrade\s+[0-9]+\b",
            r"\bmetastatic\b",
            r"\brecurrent\b",
            r"\brefractory\b",
            r"\badvanced\b",
            r"\bsevere\b",
            r"\bmild\b",
            r"\bmoderate\b",
            r"\bacute\b",
            r"\bchronic\b",
            r"\bpositive\b",
            r"\bnegative\b",
            r"\begfr[\+\-]?\b",
            r"\bher2[\+\-]?\b",
            r"\bbrca[12]?\b",
        ]
        relaxed = query
        for pattern in qualifiers:
            relaxed = re.sub(pattern, "", relaxed, flags=re.IGNORECASE)

        # Clean multiple spaces and trailing hyphens/punctuation
        relaxed = re.sub(r"[\s\-_]+", " ", relaxed).strip()
        return relaxed if len(relaxed) >= 3 else None
