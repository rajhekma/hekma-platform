"""Compatibility wrapper: matching tables are created with the full schema."""

from repositories.trialgpt_schema_bootstrap import (
    ensure_trialgpt_schema,
    reset_trialgpt_schema_for_tests,
)


def ensure_matching_pipeline_tables() -> None:
    """Create matching_jobs + result tables (and the rest of TrialGPT schema)."""
    ensure_trialgpt_schema()


def reset_matching_pipeline_schema_for_tests() -> None:
    """Clear the in-process schema cache. Tests only."""
    reset_trialgpt_schema_for_tests()
