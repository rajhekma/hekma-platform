"""Load and validate trial_gpt_ehr ingest / P2T summary-mode configuration."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, FrozenSet, Tuple


DEFAULT_CONFIG_PATH = Path(__file__).with_name("trial_gpt_ehr_config.json")
CONFIG_PATH_ENV = "TRIAL_GPT_EHR_CONFIG_PATH"

_ALLOWED_MODES = frozenset({"llm", "rule_based"})


@dataclass(frozen=True)
class TrialGptEhrConfig:
    """Validated settings for Fasten → trial_gpt_ehr ingest and P2T read path."""

    fasten_patient_created_at_cutoff: datetime
    mysql_patient_created_date_cutoff: date
    summary_modes: Tuple[str, ...]
    p2t_preferred_llm: bool
    skip_large_tables: bool

    @property
    def required_llm_flags(self) -> FrozenSet[bool]:
        """Boolean llm column values that must be ingested for this config."""
        flags = set()
        if "llm" in self.summary_modes:
            flags.add(True)
        if "rule_based" in self.summary_modes:
            flags.add(False)
        return frozenset(flags)

    @classmethod
    def load(cls, path: Path) -> "TrialGptEhrConfig":
        """Load JSON config; fail closed on invalid or inconsistent settings."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError(f"trial_gpt_ehr config not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"trial_gpt_ehr config is invalid JSON: {path}") from exc

        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TrialGptEhrConfig":
        """Build config from a dict (tests / in-memory overrides)."""
        if not isinstance(payload, dict):
            raise ValueError("trial_gpt_ehr config payload must be an object")

        cutoff_raw = str(payload.get("fastenPatientCreatedAtCutoff") or "").strip()
        if not cutoff_raw:
            raise ValueError("trial_gpt_ehr config requires fastenPatientCreatedAtCutoff")
        try:
            fasten_cutoff = datetime.fromisoformat(cutoff_raw)
        except ValueError as exc:
            raise ValueError(
                f"Invalid fastenPatientCreatedAtCutoff '{cutoff_raw}'"
            ) from exc

        mysql_cutoff_raw = str(
            payload.get("mysqlPatientCreatedDateCutoff") or "2026-08-06"
        ).strip()
        try:
            mysql_cutoff = date.fromisoformat(mysql_cutoff_raw)
        except ValueError as exc:
            raise ValueError(
                f"Invalid mysqlPatientCreatedDateCutoff '{mysql_cutoff_raw}'"
            ) from exc

        modes_raw = payload.get("summaryModes")
        if not isinstance(modes_raw, list) or not modes_raw:
            raise ValueError("trial_gpt_ehr config requires non-empty summaryModes")

        modes: list[str] = []
        seen: set[str] = set()
        for item in modes_raw:
            mode = str(item or "").strip().lower()
            if mode not in _ALLOWED_MODES:
                raise ValueError(
                    f"Invalid summaryModes entry '{item}'. "
                    f"Allowed: {sorted(_ALLOWED_MODES)}"
                )
            if mode not in seen:
                seen.add(mode)
                modes.append(mode)

        preferred = payload.get("p2tPreferredLlm")
        if not isinstance(preferred, bool):
            raise ValueError("trial_gpt_ehr config requires boolean p2tPreferredLlm")

        if preferred and "llm" not in modes:
            raise ValueError(
                "p2tPreferredLlm=true requires 'llm' in summaryModes"
            )
        if not preferred and "rule_based" not in modes:
            raise ValueError(
                "p2tPreferredLlm=false requires 'rule_based' in summaryModes"
            )

        skip_large = payload.get("skipLargeTables", True)
        if not isinstance(skip_large, bool):
            raise ValueError("skipLargeTables must be a boolean when provided")

        return cls(
            fasten_patient_created_at_cutoff=fasten_cutoff,
            mysql_patient_created_date_cutoff=mysql_cutoff,
            summary_modes=tuple(modes),
            p2t_preferred_llm=preferred,
            skip_large_tables=skip_large,
        )


def resolve_config_path() -> Path:
    """Resolve config path from env override or package default."""
    override = os.getenv(CONFIG_PATH_ENV, "").strip()
    return Path(override) if override else DEFAULT_CONFIG_PATH


@lru_cache(maxsize=1)
def get_trial_gpt_ehr_config() -> TrialGptEhrConfig:
    """Cached process-wide config load."""
    return TrialGptEhrConfig.load(resolve_config_path())


def clear_trial_gpt_ehr_config_cache() -> None:
    """Clear cached config (tests)."""
    get_trial_gpt_ehr_config.cache_clear()


def is_trialmatch_standalone_mode() -> bool:
    """True when Trial Match runs without Fasten/MySQL (FHIR upload / local corpus only)."""
    explicit = os.getenv("TRIALMATCH_STANDALONE", "").strip().lower()
    if explicit in ("1", "true", "yes"):
        return True
    if explicit in ("0", "false", "no"):
        return False
    return not bool(os.getenv("MYSQL_HOST", "").strip())
