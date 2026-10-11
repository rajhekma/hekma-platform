from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class EHRSummaryRequest(BaseModel):
    patient_id: Optional[str] = None
    email: Optional[str] = None

    @field_validator("patient_id", "email", mode="before")
    @classmethod
    def strip_whitespace(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if isinstance(v, str) else v


# ---------------------------------------------------------------------------
# Individual timeline event
# ---------------------------------------------------------------------------

class TimelineEvent(BaseModel):
    event_id: str
    category: str
    resource_type: str
    source_table: str
    resource_id: str
    date: Optional[str] = None
    date_precision: str = "unknown"          # "full", "partial", "unknown"
    summary: str
    original_record: Optional[Dict[str, Any]] = None  # omitted when include_records=false
    db_row_id: int                           # PK of the source table row


# ---------------------------------------------------------------------------
# Per-category group
# ---------------------------------------------------------------------------

class CategoryGroup(BaseModel):
    category: str
    event_count: int
    events: List[TimelineEvent]


# ---------------------------------------------------------------------------
# Patient demographics (derived from fastenhealth_patient raw_resource)
# ---------------------------------------------------------------------------

class PatientInfo(BaseModel):
    patient_id: str
    hekma_mail_id: Optional[str] = None
    name: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    summary: Optional[str] = None   # AI-generated 6-7 line clinical overview of the patient


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------

class OpenAIUsage(BaseModel):
    """OpenAI token usage for this HTTP request (zeros on cache HIT)."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0


class EHRSummaryResponse(BaseModel):
    patient: PatientInfo
    generated_at: str
    total_records_processed: int
    timeline: List[TimelineEvent]            # all events sorted chronologically
    categories: List[CategoryGroup]          # same events grouped by category
    data_integrity_notice: str = (
        "AI-generated summaries are derived solely from imported EHR records. "
        "No clinical conclusions, diagnoses, or recommendations have been added. "
        "All original source records are preserved and accessible via 'original_record'."
    )
    # ── Cache metadata ──────────────────────────────────────────────────────
    cache_hit: bool = False                  # True when response served from cache
    cache_expires_at: Optional[str] = None  # ISO-8601 UTC expiry of cached result
    openai_usage: OpenAIUsage = OpenAIUsage()  # LLM tokens consumed by this request
