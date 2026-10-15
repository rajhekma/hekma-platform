from dotenv import load_dotenv
load_dotenv()
import os
import sys
import importlib.util
from openai import OpenAI

# Allow ingest scripts to import shared Qdrant config from project root.
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.append(_ROOT)

# TrialGPT_RAG/utils.py shadows the repo-level utils package when cwd is TrialGPT_RAG.
_qdrant_util_path = os.path.join(_ROOT, "utils", "qdrant_util.py")
_spec = importlib.util.spec_from_file_location("trailgpt_qdrant_util", _qdrant_util_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
get_qdrant_client = _mod.get_qdrant_client

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
qdrant = get_qdrant_client()

COLLECTION = "clinical_trials_hybrid_v1"
DENSE_DIM  = 3072
DENSE_VEC  = "dense_medical"
SPARSE_VEC = "bm25_sparse"
TRIAL_COLLECTION = COLLECTION
PATIENT_COLLECTION = "patient_profiles_hybrid_v1"

LLM_MODEL  = "gpt-4o"

PATIENT_EXTRACTION_PROMPT = """
You are a clinical NLP system. Extract a structured patient profile from the note below.
Respond ONLY with a valid JSON object — no preamble, no markdown, no explanation.

Fields:
- age: integer or null
- sex: "Male" | "Female" | "Unknown"
- diseases: list of strings (primary disease, subtypes, and chief complaints; if no formal diagnosis include clinical presentations e.g. ["chest pain", "acute coronary syndrome", "dyspnea"])
- biomarkers: list of strings (mutations, receptors, lab markers)
- stage_severity: string or null (e.g. "metastatic", "Stage III", "NYHA Class II")
- prior_therapies: list of strings (prior drugs, chemo, radiation, surgery)
- current_medications: list of strings
- comorbidities: list of strings (chronic conditions)
- lab_values: dict of string->string for any explicit labs, or {}
- performance_status: string or null (e.g. "ECOG 1", "KPS 80")
- smoking_substance_history: string or null
- key_constraints: list of strings for anything clinically notable not captured above

Patient note:
{note}
""".strip()

QUERY_EXPANSION_PROMPT = """
You are a clinical trial search expert. Given a structured patient profile, generate a flat list of BM25-optimized search terms for finding relevant clinical trials.
Respond ONLY with a valid JSON array of strings — no preamble, no markdown.

Rules:
- Include disease synonyms, abbreviations, and related clinical terms
- Include drug class names and specific drug names relevant to the conditions
- Include relevant biomarkers, lab terms, and procedure names
- Be specific to the patient's conditions, not generic medical terms
- Include drug classes and specific interventions the patient has NOT yet received but would qualify for based on their condition
- Include trial types relevant to the patient's condition (e.g. "hypertension management", "cardiac risk reduction", "first line therapy")
- If the patient takes no medications or has no prior therapies, include terms like "treatment naive", "drug naive", "first line"
- Reason about what trials this patient would QUALIFY FOR, not just what they currently have
- Aim for 30-50 terms

Patient profile:
{profile}
""".strip()