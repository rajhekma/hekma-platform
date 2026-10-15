"""
Pydantic data models for search and matching requests.
"""

import re
from typing import Optional
from pydantic import BaseModel, Field


class PatientProfile(BaseModel):
    """Patient clinical and demographic profile."""
    age: Optional[float] = Field(default=None, description="Patient age in years.")
    sex: Optional[str] = Field(default=None, description="Patient biological sex: 'FEMALE', 'MALE', or None.")
    condition: Optional[str] = Field(default=None, description="Primary diagnosed condition.")
    clinical_note: Optional[str] = Field(default=None, description="Free text clinical notes / EHR summary.")
    sentences: list[str] = Field(default_factory=list, description="Numbered clinical sentences.")

    def model_post_init(self, __context):
        # Automatically split clinical_note into discrete numbered sentences if not already split
        if self.clinical_note and not self.sentences:
            raw_sents = re.split(r'(?<=[.!?])\s+', self.clinical_note.strip())
            self.sentences = [s.strip() for s in raw_sents if s.strip()]

    def formatted_sentences_text(self) -> str:
        """Formats patient sentences with ID prefixes for LLM citation."""
        if not self.sentences and self.clinical_note:
            return f"0: {self.clinical_note}"
        return "\n".join(f"{idx}: {sentence}" for idx, sentence in enumerate(self.sentences))


# Built-in US Major Metros & Zip Code Geocoding Database
KNOWN_US_GEO: dict[str, tuple[float, float]] = {
    # Massachusetts & Boston Metro
    "boston": (42.3601, -71.0589),
    "boston, ma": (42.3601, -71.0589),
    "cambridge": (42.3736, -71.1097),
    "cambridge, ma": (42.3736, -71.1097),
    "02115": (42.3398, -71.1017),
    "02114": (42.3627, -71.0691),
    "02138": (42.3770, -71.1256),
    "02215": (42.3472, -71.1026),
    # New York Metro
    "new york": (40.7128, -74.0060),
    "new york, ny": (40.7128, -74.0060),
    "nyc": (40.7128, -74.0060),
    "brooklyn": (40.6782, -73.9442),
    "manhattan": (40.7831, -73.9712),
    "queens": (40.7282, -73.7949),
    "10001": (40.7501, -73.9996),
    "10065": (40.7648, -73.9634),
    "10021": (40.7697, -73.9586),
    # Pennsylvania
    "philadelphia": (39.9526, -75.1652),
    "philadelphia, pa": (39.9526, -75.1652),
    "19104": (39.9566, -75.2014),
    "pittsburgh": (40.4406, -79.9959),
    "pittsburgh, pa": (40.4406, -79.9959),
    # Washington DC & Mid-Atlantic
    "washington": (38.9072, -77.0369),
    "washington, dc": (38.9072, -77.0369),
    "dc": (38.9072, -77.0369),
    "baltimore": (39.2904, -76.6122),
    "baltimore, md": (39.2904, -76.6122),
    # Illinois & Midwest
    "chicago": (41.8781, -87.6298),
    "chicago, il": (41.8781, -87.6298),
    "60611": (41.8986, -87.6202),
    "detroit": (42.3314, -83.0458),
    "minneapolis": (44.9778, -93.2650),
    "st. louis": (38.6270, -90.1994),
    "cleveland": (41.4993, -81.6944),
    "columbus": (39.9612, -82.9988),
    "cincinnati": (39.1031, -84.5120),
    "indianapolis": (39.7684, -86.1581),
    # Texas
    "houston": (29.7604, -95.3698),
    "houston, tx": (29.7604, -95.3698),
    "77030": (29.7108, -95.3977),
    "dallas": (32.7767, -96.7970),
    "dallas, tx": (32.7767, -96.7970),
    "austin": (30.2672, -97.7431),
    "austin, tx": (30.2672, -97.7431),
    "san antonio": (29.4241, -98.4936),
    # California & West Coast
    "los angeles": (34.0522, -118.2437),
    "los angeles, ca": (34.0522, -118.2437),
    "la": (34.0522, -118.2437),
    "90095": (34.0689, -118.4452),
    "90210": (34.0901, -118.4065),
    "san francisco": (37.7749, -122.4194),
    "san francisco, ca": (37.7749, -122.4194),
    "sf": (37.7749, -122.4194),
    "94102": (37.7776, -122.4199),
    "94143": (37.7631, -122.4578),
    "san diego": (32.7157, -117.1611),
    "san diego, ca": (32.7157, -117.1611),
    "san jose": (37.3382, -121.8863),
    "seattle": (47.6062, -122.3321),
    "seattle, wa": (47.6062, -122.3321),
    "98109": (47.6322, -122.3486),
    "portland": (45.5152, -122.6784),
    # Southeast
    "atlanta": (33.7490, -84.3880),
    "atlanta, ga": (33.7490, -84.3880),
    "miami": (25.7617, -80.1918),
    "miami, fl": (25.7617, -80.1918),
    "tampa": (27.9506, -82.4572),
    "orlando": (28.5383, -81.3792),
    "nashville": (36.1627, -86.7816),
    "charlotte": (35.2271, -80.8431),
    "raleigh": (35.7796, -78.6382),
    "durham": (35.9940, -78.8986),
    # Mountain & Southwest
    "denver": (39.7392, -104.9903),
    "denver, co": (39.7392, -104.9903),
    "phoenix": (33.4484, -112.0740),
    "phoenix, az": (33.4484, -112.0740),
    "las vegas": (36.1699, -115.1398),
    "salt lake city": (40.7608, -111.8910),
}


def resolve_geo_location(loc_str: str) -> Optional[tuple[float, float]]:
    """Resolves a city name, state, or zip code string to (latitude, longitude)."""
    if not loc_str:
        return None
    s = loc_str.strip().lower()

    # 1. Check direct lat, lon coordinates (e.g. "42.36, -71.05")
    lat_lon_match = re.match(r"^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$", s)
    if lat_lon_match:
        try:
            return float(lat_lon_match.group(1)), float(lat_lon_match.group(2))
        except ValueError:
            pass

    # 2. Check exact matches in known table
    if s in KNOWN_US_GEO:
        return KNOWN_US_GEO[s]

    # 3. Substring matching in known table
    for key, coords in KNOWN_US_GEO.items():
        if key in s or s in key:
            return coords

    # 4. Check 5-digit US zip code prefix lookups
    zip_match = re.search(r"\b(\d{5})\b", s)
    if zip_match:
        zip_code = zip_match.group(1)
        if zip_code in KNOWN_US_GEO:
            return KNOWN_US_GEO[zip_code]

    return None


class GeoFilter(BaseModel):
    """Geographic proximity filter for searching trials within a radius."""
    city_or_zip: Optional[str] = Field(default=None, description="City, State, or US Zip Code (e.g. 'Boston, MA', '90210'). Automatically resolved to lat/long.")
    latitude: Optional[float] = Field(default=None, description="Decimal latitude of center point (-90 to 90).")
    longitude: Optional[float] = Field(default=None, description="Decimal longitude of center point (-180 to 180).")
    radius_miles: float = Field(default=30.0, ge=1.0, le=500.0, description="Search radius in miles (default: 30.0 miles).")
    distance_miles: Optional[float] = Field(default=None, description="Alias for radius_miles.")

    def model_post_init(self, __context):
        if self.distance_miles is not None:
            self.radius_miles = self.distance_miles
        if self.city_or_zip and (self.latitude is None or self.longitude is None):
            coords = resolve_geo_location(self.city_or_zip)
            if coords:
                self.latitude, self.longitude = coords


class DemographicsInput(BaseModel):
    """Direct patient demographic input (Age & Sex) for streamlined search."""
    age: Optional[float] = Field(default=None, ge=0.0, le=125.0, description="Patient age in years.")
    sex: Optional[str] = Field(default=None, description="Patient biological sex: 'FEMALE', 'MALE', or 'ALL'.")


class QuestionAnswer(BaseModel):
    """Single user answer to an eligibility questionnaire question."""
    question_id: str = Field(..., description="Question identifier (e.g. 'q1', 'inc_0', 'exc_1').")
    answer: str = Field(..., description="User answer choice: 'YES', 'NO', or 'NOT_SURE'.")


class EligibilityEvaluationRequest(BaseModel):
    """Request payload for evaluating patient answers against study protocol."""
    nct_id: str = Field(..., description="ClinicalTrials.gov NCT identifier.")
    answers: list[QuestionAnswer] = Field(default_factory=list, description="List of question answers.")


class ConditionSearchRequest(BaseModel):
    """Simple condition search query parameters."""
    condition: str = Field(..., description="Target condition or disease to search.")
    statuses: Optional[list[str]] = Field(default=None, description="ClinicalTrials overallStatus filters.")
    page_size: int = Field(default=20, ge=1, le=100, description="Results per page.")
    page_token: Optional[str] = Field(default=None, description="Next page token for pagination.")
    count_total: bool = Field(default=True, description="Whether to request total result count from API.")


class MatchRequest(BaseModel):
    """Complete condition-to-trial matching request with 100% offline rule-based evaluation."""
    condition: str = Field(..., description="Target condition or disease to query on ClinicalTrials.gov (e.g. 'non-small cell lung cancer', 'type 2 diabetes').")
    city_or_zip: Optional[str] = Field(default=None, description="City, State, or US Zip Code for geographic proximity search (e.g. 'Boston, MA', '90210', 'New York', 'Houston'). Automatically resolved to coordinates.")
    search_radius_miles: Optional[float] = Field(default=30.0, ge=1.0, le=500.0, description="Search radius in miles around city_or_zip (default: 30.0 miles).")
    geo_filter: Optional[GeoFilter] = Field(default=None, description="Optional geographic proximity radius filter (coordinates or city/zip).")
    patient: Optional[PatientProfile] = Field(default=None, description="Optional patient profile for criteria evaluation.")
    demographics: Optional[DemographicsInput] = Field(default=None, description="Streamlined age/sex demographics (Flow 1: from profile, Flow 2: from user prompt).")
    page_size: int = Field(default=10, ge=1, le=100, description="Results per page (default: 10 for paginated matching).")
    max_trials: Optional[int] = Field(default=None, ge=1, le=100, description="Alias for page_size for backward compatibility.")
    page_token: Optional[str] = Field(default=None, description="ClinicalTrials.gov pagination token for retrieving the next page of 10 studies.")
    max_criteria_evals: Optional[int] = Field(default=None, description="Max candidate trials to evaluate against inclusion/exclusion criteria. If omitted or null, evaluates all retrieved candidates on the page.")
    max_llm_evals: Optional[int] = Field(default=None, description="Deprecated alias for max_criteria_evals (backward compatibility).")
    recruiting_only: bool = Field(default=True, description="Filter for actively recruiting studies only (overallStatus=RECRUITING).")
    force_refresh: bool = Field(default=False, description="Bypass PostgreSQL cache and force fresh fetch from ClinicalTrials.gov.")
    provider: Optional[str] = Field(default="heuristic", description="Offline rule-based engine: 'heuristic'.")

    def model_post_init(self, __context):
        # 1. Automatic GeoFilter resolution from top-level city_or_zip & search_radius_miles
        if self.city_or_zip and not self.geo_filter:
            coords = resolve_geo_location(self.city_or_zip)
            rad = self.search_radius_miles or 30.0
            if coords:
                self.geo_filter = GeoFilter(
                    city_or_zip=self.city_or_zip,
                    latitude=coords[0],
                    longitude=coords[1],
                    radius_miles=rad,
                )
            else:
                self.geo_filter = GeoFilter(
                    city_or_zip=self.city_or_zip,
                    radius_miles=rad,
                )
        elif self.geo_filter:
            if not self.city_or_zip and self.geo_filter.city_or_zip:
                self.city_or_zip = self.geo_filter.city_or_zip
            if self.geo_filter.radius_miles:
                self.search_radius_miles = self.geo_filter.radius_miles

        # 2. Streamlined demographics: build patient profile automatically if provided
        if self.demographics and self.patient is None:
            self.patient = PatientProfile(
                age=self.demographics.age,
                sex=self.demographics.sex,
                condition=self.condition,
            )
        # 3. Backwards compatibility: map max_llm_evals -> max_criteria_evals
        if self.max_criteria_evals is None and self.max_llm_evals is not None:
            self.max_criteria_evals = self.max_llm_evals
        if self.max_trials is not None and self.page_size == 10:
            self.page_size = self.max_trials

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "condition": "non-small cell lung cancer",
                    "city_or_zip": "Boston, MA",
                    "search_radius_miles": 30.0,
                    "demographics": {
                        "age": 52,
                        "sex": "FEMALE"
                    },
                    "page_size": 10,
                    "page_token": None,
                    "recruiting_only": True
                }
            ]
        }
    }

