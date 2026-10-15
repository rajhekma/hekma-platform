"""Canonical paths for P2T dev datasets."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Active dev eval: 1 patient × 10 trials (corpus annot_10)
EVAL_PATIENT_SUBJECT_ID = "004fec23-6023-572a-922e-6d73b325e771"
EVAL_CORPUS = "annot_10"

SINGLE_PATIENT_LOAD_JSON = _REPO_ROOT / "dataset" / "single_patient_load.json"
CORPUS_ANNOT_10_JSONL = _REPO_ROOT / "dataset" / "corpus_annot_10.jsonl"
TRIALS_JSONL = _REPO_ROOT / "dataset" / "trials.jsonl"

# Legacy 20-patient cohort (deferred; not used in current API eval)
ANNOT_20_PATIENT_P2T_JSON = _REPO_ROOT / "dataset" / "annot_20_patient.json"
ANNOT_20_PATIENT_P2T_JSON_LEGACY = (
    _REPO_ROOT / "dataset" / "block_summary" / "annot_20_patient (1).json"
)
