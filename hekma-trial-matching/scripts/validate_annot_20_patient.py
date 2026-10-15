"""
Validate dataset/block_summary/annot_20_patient (1).json structure and counts.

Usage (from repo root):
  python scripts/validate_annot_20_patient.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from dataset.block_summary.paths import ANNOT_20_PATIENT_P2T_JSON

REQUIRED_PATIENT_KEYS = {"Patient_ID", "Patient_Summary", "Patient_Block_Summary", "Trials"}
REQUIRED_TRIAL_KEYS = {
    "Trail_ID",
    "Trail_text",
    "Matching_Results",
}


def main() -> int:
    path = ANNOT_20_PATIENT_P2T_JSON
    if not path.is_file():
        print(f"FAIL: missing file: {path}")
        return 1

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("FAIL: root JSON must be a list of patients")
        return 1

    n_patients = len(data)
    trial_counts: list[int] = []
    total_trials = 0
    patient_ids: list[str] = []

    for i, row in enumerate(data):
        if not isinstance(row, dict):
            print(f"FAIL: patient index {i} is not an object")
            return 1
        missing = REQUIRED_PATIENT_KEYS - row.keys()
        if missing:
            print(f"FAIL: patient index {i} missing keys: {sorted(missing)}")
            return 1
        pid = row.get("Patient_ID")
        if not pid:
            print(f"FAIL: patient index {i} empty Patient_ID")
            return 1
        patient_ids.append(str(pid))

        trials = row.get("Trials")
        if not isinstance(trials, list):
            print(f"FAIL: patient {pid} Trials is not a list")
            return 1
        trial_counts.append(len(trials))
        total_trials += len(trials)

        for j, t in enumerate(trials):
            if not isinstance(t, dict):
                print(f"FAIL: patient {pid} trial index {j} not an object")
                return 1
            tm = REQUIRED_TRIAL_KEYS - t.keys()
            if tm:
                print(f"FAIL: patient {pid} trial {j} missing keys: {sorted(tm)}")
                return 1
            mr = t.get("Matching_Results")
            if not isinstance(mr, dict) or "inclusion" not in mr or "exclusion" not in mr:
                print(f"FAIL: patient {pid} trial {j} Matching_Results must have inclusion/exclusion")
                return 1

    dup = [x for x in patient_ids if patient_ids.count(x) > 1]
    if dup:
        print(f"FAIL: duplicate Patient_ID values: {set(dup)}")
        return 1

    print(f"OK: file={path}")
    print(f"  patients={n_patients}")
    print(f"  trials_per_patient min={min(trial_counts)} max={max(trial_counts)} total_trial_rows={total_trials}")
    if n_patients != 20:
        print(f"WARN: expected 20 patients, got {n_patients}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
