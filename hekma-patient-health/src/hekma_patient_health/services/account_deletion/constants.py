"""Configurable retention and confirmation constants for account deletion."""

from __future__ import annotations

import os

CONFIRM_PHRASE = "DELETE"

# Step 6: PHI hard-delete delay after archive. Default 6 years; override via env.
DEFAULT_PHI_RETENTION_YEARS = 6


def phi_retention_years() -> int:
    """Years PHI stays locked in archive before scheduled hard purge."""
    raw = os.getenv("ACCOUNT_DELETION_PHI_RETENTION_YEARS", str(DEFAULT_PHI_RETENTION_YEARS))
    try:
        years = int(str(raw).strip())
    except (TypeError, ValueError):
        years = DEFAULT_PHI_RETENTION_YEARS
    return max(years, 0)


def phi_retention_days() -> int:
    """Day-level override wins when set (useful for staging tests)."""
    raw = os.getenv("ACCOUNT_DELETION_PHI_RETENTION_DAYS")
    if raw is None or str(raw).strip() == "":
        return phi_retention_years() * 365
    try:
        days = int(str(raw).strip())
    except (TypeError, ValueError):
        return phi_retention_years() * 365
    return max(days, 0)
