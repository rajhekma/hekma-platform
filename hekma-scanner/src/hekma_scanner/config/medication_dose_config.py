"""Load and validate configurable medication dose slots and fallback timezone."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo


DEFAULT_CONFIG_PATH = Path(__file__).with_name("medication_dose_config.json")
CONFIG_PATH_ENV = "MEDICATION_DOSE_CONFIG_PATH"


def _parse_clock(value: Any, *, allow_midnight_end: bool = False) -> int:
    """Parse HH:MM into minutes after midnight; optionally accept 24:00."""
    text = str(value or "").strip()
    try:
        hour_text, minute_text = text.split(":", 1)
        hour, minute = int(hour_text), int(minute_text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid medication slot time '{text}'; expected HH:MM") from exc

    if allow_midnight_end and hour == 24 and minute == 0:
        return 24 * 60
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"Invalid medication slot time '{text}'; expected 00:00–23:59")
    return hour * 60 + minute


@dataclass(frozen=True)
class MedicationDoseSlot:
    """One named local-clock window and its accepted reminder labels."""

    name: str
    start_minute: int
    end_minute: int
    labels: Tuple[str, ...]


class MedicationDoseConfig:
    """Validated medication timing configuration loaded from JSON."""

    def __init__(
        self,
        default_timezone: str,
        slots: Tuple[MedicationDoseSlot, ...],
        edit_window_hours: int = 24,
    ):
        self.default_timezone = default_timezone
        self.slots = slots
        self.edit_window_hours = edit_window_hours
        self._labels: Dict[str, MedicationDoseSlot] = {
            label.strip().lower(): slot
            for slot in slots
            for label in slot.labels
        }

    @classmethod
    def load(cls, path: Path) -> "MedicationDoseConfig":
        """Load a JSON config file and fail fast on invalid or overlapping slots."""
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError(f"Medication dose config not found: {path}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Medication dose config is invalid JSON: {path}") from exc

        timezone_name = str(payload.get("defaultTimezone") or "").strip()
        if not timezone_name:
            raise ValueError("Medication dose config requires defaultTimezone")
        try:
            ZoneInfo(timezone_name)
        except Exception as exc:
            raise ValueError(
                f"Invalid medication defaultTimezone '{timezone_name}'"
            ) from exc

        edit_window_hours = payload.get("editWindowHours", 24)
        try:
            edit_window_hours = int(edit_window_hours)
        except (TypeError, ValueError) as exc:
            raise ValueError("editWindowHours must be an integer") from exc
        if edit_window_hours < 1 or edit_window_hours > 168:
            raise ValueError("editWindowHours must be between 1 and 168")

        raw_slots = payload.get("slots")
        if not isinstance(raw_slots, list) or not raw_slots:
            raise ValueError("Medication dose config requires a non-empty slots array")

        slots = tuple(cls._parse_slot(item) for item in raw_slots)
        cls._validate_slots(slots)
        return cls(timezone_name, slots, edit_window_hours=edit_window_hours)

    @staticmethod
    def _parse_slot(item: Any) -> MedicationDoseSlot:
        """Parse one slot object from the JSON configuration."""
        if not isinstance(item, dict):
            raise ValueError("Each medication slot must be an object")
        name = str(item.get("name") or "").strip()
        labels = tuple(
            str(label).strip()
            for label in (item.get("labels") or [])
            if str(label).strip()
        )
        if not name or not labels:
            raise ValueError("Each medication slot requires name and labels")
        start = _parse_clock(item.get("start"))
        end = _parse_clock(item.get("end"), allow_midnight_end=True)
        if end <= start:
            raise ValueError(f"Medication slot '{name}' end must be after start")
        return MedicationDoseSlot(name, start, end, labels)

    @staticmethod
    def _validate_slots(slots: Tuple[MedicationDoseSlot, ...]) -> None:
        """Reject duplicate names/labels and overlapping configured windows."""
        names = [slot.name.lower() for slot in slots]
        labels = [label.lower() for slot in slots for label in slot.labels]
        if len(names) != len(set(names)):
            raise ValueError("Medication slot names must be unique")
        if len(labels) != len(set(labels)):
            raise ValueError("Medication slot labels must be unique")

        ordered = sorted(slots, key=lambda slot: slot.start_minute)
        for previous, current in zip(ordered, ordered[1:]):
            if previous.end_minute > current.start_minute:
                raise ValueError(
                    f"Medication slots '{previous.name}' and '{current.name}' overlap"
                )

    def slot_for_label(self, label: Any) -> Optional[MedicationDoseSlot]:
        """Resolve a configured slot from a case-insensitive reminder label."""
        key = str(getattr(label, "value", label) or "").strip().lower()
        return self._labels.get(key)

    def slot_for_minute(self, minute: int) -> MedicationDoseSlot:
        """Resolve a local-clock minute, including gaps used by legacy schedules."""
        for slot in self.slots:
            if slot.start_minute <= minute < slot.end_minute:
                return slot

        ordered = sorted(self.slots, key=lambda slot: slot.start_minute)
        previous = ordered[-1]
        for slot in ordered:
            if minute < slot.start_minute:
                return previous
            previous = slot
        return previous

    def next_boundary_minute(self, minute: int) -> int:
        """Return the next configured slot boundary after a local-clock minute."""
        slot = self.slot_for_minute(minute)
        if slot.start_minute <= minute < slot.end_minute:
            return slot.end_minute

        later_starts = sorted(
            configured.start_minute
            for configured in self.slots
            if configured.start_minute > minute
        )
        return later_starts[0] if later_starts else 24 * 60


@lru_cache(maxsize=1)
def get_medication_dose_config() -> MedicationDoseConfig:
    """Return the process-wide dose configuration; restart after file changes."""
    configured_path = os.getenv(CONFIG_PATH_ENV, "").strip()
    path = Path(configured_path).expanduser() if configured_path else DEFAULT_CONFIG_PATH
    return MedicationDoseConfig.load(path)
