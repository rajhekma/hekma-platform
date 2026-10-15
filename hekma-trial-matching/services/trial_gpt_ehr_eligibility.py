"""Pure eligibility helpers for trial_gpt_ehr (no DB imports)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

from config.trial_gpt_ehr_config import TrialGptEhrConfig


def as_date(value: Any) -> Optional[date]:
    """Coerce DB/date-like values to date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def as_naive_datetime(value: Any) -> Optional[datetime]:
    """Coerce DB/datetime-like values to naive datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


def is_cutoff_eligible(
    *,
    mysql_created_at: Any,
    fasten_created_at: Any,
    config: TrialGptEhrConfig,
) -> bool:
    """
    True when patient qualifies for trial_gpt_ehr path.

    Fasten created_at cutoff is required. MySQL created date is enforced when
    the Patient table exposes a created column; otherwise Fasten alone gates.
    """
    fasten_ts = as_naive_datetime(fasten_created_at)
    if not fasten_ts:
        return False
    if fasten_ts < config.fasten_patient_created_at_cutoff:
        return False

    mysql_day = as_date(mysql_created_at)
    if mysql_day is not None and mysql_day < config.mysql_patient_created_date_cutoff:
        return False
    return True
