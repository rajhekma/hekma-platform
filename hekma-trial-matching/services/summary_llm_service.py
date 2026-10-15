import json

from services.llm_invoke import complete_json_object, complete_text
from utils.llm_config import resolve_compose_llm_service, resolve_compose_model


def generate_summary(structured_json, *, model=None, llm_service=None):
    model = resolve_compose_model(model)
    llm_service = resolve_compose_llm_service(llm_service)

    system_prompt = """
    You are a clinical data summarization engine.

    Your task is to convert structured patient clinical data into a compact,
    objective, trial-matching style clinical summary.

    Strict rules:
    - Do NOT add interpretations.
    - Do NOT add commentary.
    - Do NOT add phrases like "currently has no documented".
    - Do NOT restate empty categories.
    - If data is missing, ignore it silently.
    - Do NOT fabricate.
    - Do NOT mention that data is missing.
    - No headings.
    - No bullet points.
    - No conclusions.
    - No recommendations.

    Style:
    - Write like a clinical case summary used in research datasets.
    - Use concise medical phrasing.
    - Include diagnoses, treatments, procedures, imaging, labs, medications, symptoms.
    - Maintain chronological flow if possible.
    - One paragraph only.

    Return only the summary text.
    """
    return complete_text(
        system_prompt,
        str(structured_json),
        model=model,
        llm_service=llm_service,
    )


def generate_disease_list(
    patient_summary,
    patient_block_summary,
    *,
    model=None,
    llm_service=None,
):
    model = resolve_compose_model(model)
    llm_service = resolve_compose_llm_service(llm_service)

    system_prompt = """
    You are an expert clinical information extraction system.

    Task: Extract all confirmed disease or condition names from the given clinical text.

    Output Requirements:

    * Return ONLY valid JSON.
    * Use this exact schema:
    {"disease_list": ["disease 1", "disease 2"]}

    Rules:

    1. Include only confirmed diagnoses or clearly stated medical conditions.
    2. Exclude symptoms, signs, procedures, lab results (e.g. leukocytosis, elevated liver enzymes), medications, demographics.
    3. Only use the "conditions" field for diagnoses; do NOT promote observation/lab rows to disease_list.
    3. Ignore ruled-out or family-history-only conditions unless confirmed.
    4. Normalize abbreviations and remove duplicates (case-insensitive).
    5. Prefer specific diagnosis names when available.

    If no diseases or conditions are found, return:
    {"disease_list": []}
    """

    user_payload = {
        "Patient_Summary": patient_summary,
        "Patient_Block_Summary": patient_block_summary,
    }

    parsed = complete_json_object(
        system_prompt,
        json.dumps(user_payload, ensure_ascii=False),
        model=model,
        llm_service=llm_service,
    )
    disease_list = parsed.get("disease_list", [])

    if not isinstance(disease_list, list):
        return []

    cleaned = []
    seen = set()
    for disease in disease_list:
        if not isinstance(disease, str):
            continue
        value = disease.strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(value)

    return cleaned
