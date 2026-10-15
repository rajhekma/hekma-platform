import json
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are a clinical data quality auditor for trial-matching patient summaries.

You receive:
1) patient_360: structured facts extracted from MIMIC FHIR source records
2) summary_text: an LLM-generated narrative summary used for trial matching
3) disease_list: normalized diseases extracted alongside the summary

Your job is to assess whether the summary is accurate and reliable relative to patient_360.

Rules:
- Treat patient_360 as ground truth
- Flag any statement in summary_text not supported by patient_360 as fabrication
- Flag clinically important patient_360 facts missing from summary_text as omission
- Do not penalize reasonable clinical paraphrasing
- Ignore minor wording differences
- Be conservative: uncertain claims are warnings, clear contradictions are failures

Return STRICT JSON:
{
  "overall_status": "pass" | "warning" | "fail",
  "reliability_score": <integer 0-100>,
  "summary": "<one sentence overall assessment>",
  "checks": [
    {
      "category": "demographics" | "conditions" | "medications" | "procedures" | "observations" | "encounters" | "diseases" | "general",
      "status": "pass" | "warning" | "fail",
      "message": "<short explanation>",
      "evidence": "<optional quote or fact from patient_360 or summary>"
    }
  ],
  "fabrications": ["<unsupported claim>", ...],
  "omissions": ["<missing important fact>", ...]
}

Scoring guide:
- pass: score >= 85, no fail checks, no fabrications
- warning: score 60-84 OR minor omissions/warnings only
- fail: score < 60 OR any fabrication OR critical clinical contradiction

Return ONLY JSON.
"""


def run_llm_validation(summary_text: str, patient_360: dict, disease_list: list, patient_id=None) -> dict:
    payload = {
        "patient_360": patient_360,
        "summary_text": summary_text,
        "disease_list": disease_list,
    }

    response = client.chat.completions.create(
        model=os.getenv("PATIENT_SUMMARY_VALIDATION_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload)},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    try:
        from services.ai_usage import emit_llm_usage

        emit_llm_usage(
            patient_id=str(patient_id) if patient_id else None,
            product="patient_summary",
            feature="patient_summary.validation",
            provider="openai",
            model=os.getenv("PATIENT_SUMMARY_VALIDATION_MODEL", "gpt-4o-mini"),
            usage=response.usage,
            source_service="hekma-trialgpt",
        )
    except Exception:
        pass

    content = response.choices[0].message.content
    parsed = json.loads(content)

    score = int(parsed.get("reliability_score", 0))
    score = max(0, min(100, score))

    status = str(parsed.get("overall_status", "warning")).lower()
    if status not in {"pass", "warning", "fail"}:
        status = "warning"

    checks = parsed.get("checks") or []
    if not isinstance(checks, list):
        checks = []

    return {
        "overall_status": status,
        "reliability_score": score,
        "summary": (parsed.get("summary") or "").strip(),
        "checks": checks,
        "fabrications": parsed.get("fabrications") or [],
        "omissions": parsed.get("omissions") or [],
        "validator": "llm",
    }
