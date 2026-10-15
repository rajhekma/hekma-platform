import json
import re
from datetime import date
from functools import wraps

from repositories.trialgpt_schema_bootstrap import ensure_trialgpt_schema
from utils.pg_util import pg_transaction


def _requires_schema(fn):
    """Create TrialGPT tables before the first compose query on a new env."""

    @wraps(fn)
    def wrapped(*args, **kwargs):
        ensure_trialgpt_schema()
        return fn(*args, **kwargs)

    return wrapped

# TrialGPT patient read/write table (replaces compose_summary_block).
COMPOSE_READ_TABLE = "trialgpt_eligible_patients"
COMPOSE_ID_COLUMN = "subject_id"


_EXPLICIT_AGE_RE = re.compile(r"(?i)\bage\b\s*[:=]|\b\d{1,3}[-\s]year[-\s]old\b")
_DOB_LABELLED_RE = re.compile(
    r"(?i)(?:date of birth|birth date|dob|born)[^\d]{0,12}(\d{4}-\d{2}-\d{2})"
)
_DOB_ANY_RE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")

# Vitals for BMI/height/weight based trial criteria. Only the adult BMI expressed in
# kg/m2 is used (the "[Percentile] Per age and gender" variant is intentionally excluded).
_HEIGHT_RE = re.compile(r"(?i)body\s*height:\s*([\d.]+)\s*cm")
_WEIGHT_RE = re.compile(r"(?i)body\s*weight:\s*([\d.]+)\s*kg")
_BMI_RE = re.compile(r"(?i)body\s*mass\s*index\s*:\s*([\d.]+)\s*kg/?\s*m2")


def _extract_birth_date(demographics, summary_text=""):
    """Pull an ISO birth date from either the structured demographics (dict or the
    flattened natural-language string) or, as a fallback, the summary text."""
    if isinstance(demographics, dict):
        bd = demographics.get("birth_date")
        if bd:
            return bd
        demographics = ""
    for text in (str(demographics or ""), str(summary_text or "")):
        m = _DOB_LABELLED_RE.search(text) or _DOB_ANY_RE.search(text)
        if m:
            return m.group(1)
    return None


def _age_from_birth_date(birth_date, as_of: date | None = None):
    """Deterministic age in years from an ISO birthDate. None if unparseable/implausible.

    The matching GLOBAL POLICY forbids the LLM from inferring age from raw dates, but
    accepts an explicit numeric age statement. We compute it here in the backend so the
    patient note carries an explicit 'Age: N' the matcher can use.
    """
    if not birth_date:
        return None
    as_of = as_of or date.today()
    try:
        bd = date.fromisoformat(str(birth_date)[:10])
    except (ValueError, TypeError):
        return None
    age = as_of.year - bd.year - ((as_of.month, as_of.day) < (bd.month, bd.day))
    return age if 0 <= age <= 120 else None


def _age_prefix(summary_text, structured_json):
    """Return an 'Age: N years.' prefix derived from structured_json demographics.

    Returns '' when age is not derivable or the summary already states an explicit age
    (avoids double-counting / contradicting an existing statement).
    """
    if not summary_text or _EXPLICIT_AGE_RE.search(summary_text):
        return ""
    data = structured_json
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return ""
    if not isinstance(data, dict):
        return ""
    birth_date = _extract_birth_date(data.get("demographics"), summary_text)
    age = _age_from_birth_date(birth_date)
    return f"Age: {age} years.\n" if age is not None else ""


def _observations_text(structured_json):
    """Return the observations block as searchable text (handles dict/str/list)."""
    data = structured_json
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return str(structured_json)
    if isinstance(data, dict):
        obs = data.get("observations")
        return obs if isinstance(obs, str) else json.dumps(obs or "")
    return ""


def _vitals_prefix(summary_text, structured_json):
    """Return an explicit 'Height/Weight/BMI' line derived from observations.

    Like age, the matcher accepts an explicit BMI/height/weight statement but won't
    compute it from scattered observations. We surface it here (using a recorded BMI in
    kg/m2 when present, else computing BMI from height+weight). Skipped when the note
    already states an explicit BMI in kg/m2.
    """
    if summary_text and _BMI_RE.search(summary_text):
        return ""
    obs = _observations_text(structured_json)
    if not obs:
        return ""

    h_m = _HEIGHT_RE.search(obs)
    w_m = _WEIGHT_RE.search(obs)
    bmi_m = _BMI_RE.search(obs)

    bmi = None
    if bmi_m:
        try:
            bmi = float(bmi_m.group(1))
        except (TypeError, ValueError):
            bmi = None
    if bmi is None and h_m and w_m:
        try:
            h_m_val = float(h_m.group(1)) / 100.0
            w_kg = float(w_m.group(1))
            if h_m_val > 0:
                bmi = round(w_kg / (h_m_val * h_m_val), 1)
        except (TypeError, ValueError):
            bmi = None

    parts = []
    if h_m:
        parts.append(f"Height: {h_m.group(1)} cm")
    if w_m:
        parts.append(f"Weight: {w_m.group(1)} kg")
    if bmi is not None and 8 <= bmi <= 100:
        parts.append(f"BMI: {bmi} kg/m2")

    return (". ".join(parts) + ".\n") if parts else ""


def _derived_prefix(summary_text, structured_json):
    """Explicit demographic/vital facts (age, height, weight, BMI) computed
    deterministically from stored structured data, so criteria matching can use them."""
    return (
        _age_prefix(summary_text, structured_json)
        + _vitals_prefix(summary_text, structured_json)
    )


def _profile_for_pipeline(structured_json):
    """Remove internal metadata before RAG / matching; normalize block values."""
    if not isinstance(structured_json, dict):
        return structured_json or {}

    out = {}
    for k, v in structured_json.items():
        if k in ("_generation", "_icd_diseases"):
            continue
        if isinstance(v, dict):
            parts = []
            for sk, sv in v.items():
                if sv is None:
                    continue
                text = str(sv).strip()
                if text:
                    parts.append(f"{sk}: {text}")
            out[k] = ", ".join(parts) if parts else None
        else:
            out[k] = v
    return out


@_requires_schema
def get_compose_timestamp(patient_id):
    """Legacy compose table timestamp (prefer get_compose_summary_block_timestamp)."""
    with pg_transaction() as (_, cur):
        cur.execute(
            "SELECT last_data_timestamp FROM compose WHERE patient_id = %s",
            (patient_id,),
        )
        row = cur.fetchone()
        return row["last_data_timestamp"] if row else None


@_requires_schema
def get_compose_summary_block_timestamp(patient_id):
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT last_data_timestamp
            FROM {COMPOSE_READ_TABLE}
            WHERE {COMPOSE_ID_COLUMN} = %s
            """,
            (patient_id,),
        )
        row = cur.fetchone()
        return row["last_data_timestamp"] if row else None


@_requires_schema
def count_compose_summary_block() -> int:
    """Count patients with structured_json ready for TrialGPT."""
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT COUNT(*) AS n
            FROM {COMPOSE_READ_TABLE}
            WHERE structured_json IS NOT NULL
              AND summary_text IS NOT NULL
              AND BTRIM(summary_text) <> ''
            """
        )
        return int(cur.fetchone()["n"])


@_requires_schema
def fetch_compose_profiles_by_ids(patient_ids: list[str]) -> dict[str, dict]:
    """Return {patient_id: structured_json} for the given subject IDs."""
    if not patient_ids:
        return {}
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT {COMPOSE_ID_COLUMN} AS patient_id, structured_json
            FROM {COMPOSE_READ_TABLE}
            WHERE {COMPOSE_ID_COLUMN} = ANY(%s)
              AND structured_json IS NOT NULL
            """,
            (list(patient_ids),),
        )
        rows = cur.fetchall() or []
    out: dict[str, dict] = {}
    for row in rows:
        pid = str(row.get("patient_id") or "").strip()
        profile = row.get("structured_json")
        if pid and isinstance(profile, dict):
            out[pid] = _profile_for_pipeline(profile)
        elif pid and isinstance(profile, str):
            try:
                parsed = json.loads(profile)
            except Exception:
                continue
            if isinstance(parsed, dict):
                out[pid] = _profile_for_pipeline(parsed)
    return out


@_requires_schema
def upsert_compose(
    patient_id,
    summary_text,
    structured_json,
    disease_list,
    last_data_timestamp,
    site_id=None,
):
    """Legacy upsert into compose table."""
    with pg_transaction() as (_, cur):
        cur.execute(
            """
            INSERT INTO compose (
                patient_id,
                summary_text,
                structured_json,
                disease_list,
                last_data_timestamp,
                site_id,
                version,
                last_generated_at
            )
            VALUES (%s, %s, %s::jsonb, %s, %s, %s, 1, NOW())
            ON CONFLICT (patient_id)
            DO UPDATE SET
                summary_text = EXCLUDED.summary_text,
                structured_json = EXCLUDED.structured_json,
                disease_list = EXCLUDED.disease_list,
                last_data_timestamp = EXCLUDED.last_data_timestamp,
                site_id = EXCLUDED.site_id,
                last_generated_at = NOW(),
                version = compose.version + 1
            """,
            (
                patient_id,
                summary_text,
                json.dumps(structured_json),
                disease_list,
                last_data_timestamp,
                site_id,
            ),
        )


@_requires_schema
def upsert_compose_summary_block(
    patient_id,
    summary_text,
    structured_json,
    disease_list,
    last_data_timestamp,
    site_id=None,
):
    """
    Upsert TrialGPT patient summary into trialgpt_eligible_patients.
    patient_id is the subject UUID (subject_id).
    """
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            INSERT INTO {COMPOSE_READ_TABLE} (
                {COMPOSE_ID_COLUMN},
                summary_text,
                structured_json,
                disease_list,
                last_data_timestamp,
                last_generated_at,
                summary_status,
                updated_at
            )
            VALUES (%s, %s, %s::jsonb, %s, %s, NOW(), 'ready', NOW())
            ON CONFLICT ({COMPOSE_ID_COLUMN})
            DO UPDATE SET
                summary_text = EXCLUDED.summary_text,
                structured_json = EXCLUDED.structured_json,
                disease_list = EXCLUDED.disease_list,
                last_data_timestamp = EXCLUDED.last_data_timestamp,
                last_generated_at = NOW(),
                summary_status = 'ready',
                updated_at = NOW()
            """,
            (
                patient_id,
                summary_text,
                json.dumps(structured_json),
                disease_list,
                last_data_timestamp,
            ),
        )


@_requires_schema
def get_patient_diseases(patient_id: str):
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT disease_list
            FROM {COMPOSE_READ_TABLE}
            WHERE {COMPOSE_ID_COLUMN} = %s
            """,
            (patient_id,),
        )
        row = cur.fetchone()

        if not row or not row["disease_list"]:
            return []

        return row["disease_list"]


@_requires_schema
def fetch_patient_icd_diseases(patient_id: str):
    """ICD-10-CM codes and official titles from structured_json._icd_diseases."""
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT structured_json
            FROM {COMPOSE_READ_TABLE}
            WHERE {COMPOSE_ID_COLUMN} = %s
            """,
            (patient_id,),
        )
        row = cur.fetchone()
        if not row or not row.get("structured_json"):
            return []
        data = row["structured_json"]
        if isinstance(data, str):
            data = json.loads(data)
        entries = data.get("_icd_diseases") if isinstance(data, dict) else []
        return entries if isinstance(entries, list) else []


@_requires_schema
def fetch_compose_summary(patient_id):
    """Fetch summary_text (with a deterministic Age line) for TrialGPT matching."""
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT summary_text, structured_json
            FROM {COMPOSE_READ_TABLE}
            WHERE {COMPOSE_ID_COLUMN} = %s
            """,
            (patient_id,),
        )
        row = cur.fetchone()
        if not row or not row.get("summary_text"):
            return None
        return _derived_prefix(row["summary_text"], row.get("structured_json")) + row["summary_text"]


@_requires_schema
def fetch_compose_structured_profile(patient_id):
    """Fetch structured_json profile for RAG / matching."""
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT structured_json
            FROM {COMPOSE_READ_TABLE}
            WHERE {COMPOSE_ID_COLUMN} = %s
            """,
            (patient_id,),
        )
        row = cur.fetchone()
        if not row or not row.get("structured_json"):
            return None
        data = row["structured_json"]
        if isinstance(data, str):
            data = json.loads(data)
        return _profile_for_pipeline(data)


@_requires_schema
def fetch_all_compose_summaries():
    """
    Fetch all patient summaries for T2P retrieval.
    Returns rows with keys patient_id, summary_text (patient_id = subject_id).
    """
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT {COMPOSE_ID_COLUMN} AS patient_id, summary_text
            FROM {COMPOSE_READ_TABLE}
            WHERE summary_text IS NOT NULL
              AND BTRIM(summary_text) <> ''
            """
        )
        return cur.fetchall()


def fetch_compose_summaries_map():
    """Fetch all patient summaries as map: patient_id -> summary_text."""
    rows = fetch_all_compose_summaries() or []
    out = {}
    for row in rows:
        pid = row.get("patient_id")
        txt = row.get("summary_text")
        if pid and txt:
            out[pid] = txt
    return out


@_requires_schema
def fetch_compose_summaries_by_ids(patient_ids: list[str]) -> dict[str, str]:
    """
    Fetch summary_text only for the given subject IDs (map: patient_id -> summary_text).

    This is the hot path for T2P: hydrate just the handful of retrieved candidates
    instead of scanning the whole trialgpt_eligible_patients table (which times out
    at ~30k rows).
    """
    if not patient_ids:
        return {}
    unique_ids = list({str(pid).strip() for pid in patient_ids if pid and str(pid).strip()})
    if not unique_ids:
        return {}
    with pg_transaction() as (_, cur):
        cur.execute(
            f"""
            SELECT {COMPOSE_ID_COLUMN} AS patient_id, summary_text, structured_json
            FROM {COMPOSE_READ_TABLE}
            WHERE {COMPOSE_ID_COLUMN} = ANY(%s)
              AND summary_text IS NOT NULL
              AND BTRIM(summary_text) <> ''
            """,
            (unique_ids,),
        )
        rows = cur.fetchall() or []
    out: dict[str, str] = {}
    for row in rows:
        pid = str(row.get("patient_id") or "").strip()
        txt = row.get("summary_text")
        if pid and txt:
            out[pid] = _derived_prefix(txt, row.get("structured_json")) + txt
    return out


@_requires_schema
def get_patient_summary(subject_id):
    """Fetch patient summary_text from trialgpt_eligible_patients."""
    with pg_transaction(dict_cursor=True) as (_, cur):
        cur.execute(
            f"""
            SELECT summary_text
            FROM {COMPOSE_READ_TABLE}
            WHERE {COMPOSE_ID_COLUMN} = %s
            """,
            (subject_id,),
        )
        row = cur.fetchone()
        if row:
            return row["summary_text"]
        return None
