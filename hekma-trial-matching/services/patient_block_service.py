"""
Generate Patient_Block_Summary JSON using Claude (or configured compose LLM).
"""

from __future__ import annotations

from services.llm_invoke import complete_json_object

BLOCK_SUMMARY_SYSTEM_PROMPT = """You are a clinical summarization assistant.

Given patient data, return ONLY a valid JSON object with exactly these 7 keys:
- demographics
- allergies
- conditions
- procedures
- medications
- observations
- immunizations

Rules:
1. Output must be a single valid JSON object.
2. Do not include markdown fences.
3. Do not include explanations or extra text.
4. Each key must always be present exactly once.
5. Each value must be either:
   - a concise plain-text summary string, or
   - null if no relevant information is available.
6. Do not invent information not supported by the patient data.
7. Keep each summary brief and factual.
8. Dates in patient data (DOB, test dates, procedure dates) may have been anonymized and are unreliable.
   Do not use any date to infer or calculate patient age.
   Only state age if it is explicitly provided as a plain value (e.g., "58-year-old" or "Age: 45").
   If no explicit age is stated, set demographics age to null or omit age entirely.
"""


def generate_block_summary_from_text(
    patient_id: str,
    summary_text: str,
    *,
    model: str | None = None,
    llm_service: str | None = None,
) -> dict:
    user_prompt = (
        f"Patient ID: {patient_id}\n\n"
        f"Patient Data:\n{summary_text}\n\n"
        "Return ONLY valid JSON. Do not include markdown fences or explanations."
    )
    return complete_json_object(
        BLOCK_SUMMARY_SYSTEM_PROMPT,
        user_prompt,
        model=model,
        llm_service=llm_service,
    )


def attach_generation_metadata(
    structured_json: dict,
    *,
    model: str,
    llm_service: str,
    steps: list[str],
) -> dict:
    """Store provenance inside structured_json (stripped before RAG/matching)."""
    out = dict(structured_json or {})
    out["_generation"] = {
        "model": model,
        "llm_service": llm_service,
        "steps": steps,
    }
    return out
