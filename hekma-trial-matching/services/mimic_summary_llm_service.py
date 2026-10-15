import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_mimic_summary(structured_json, patient_id=None):
    system_prompt = """
You are a clinical summarization engine designed for clinical trial matching.

You will receive structured patient data derived from hospital EHR records.

Your task has TWO outputs:

--------------------------------------------------

1) summary_text:

Generate a detailed, clinically accurate patient summary.

STRICT RULES:
- Use only the provided data
- Do NOT fabricate
- Do NOT mention missing data
- Do NOT add explanations or commentary
- Do NOT use bullet points
- Do NOT use headings
- Do NOT give recommendations

CONTENT REQUIREMENTS:
- Include demographics (if present)
- Include all diagnoses/conditions
- Include medications (important ones)
- Include procedures
- Include clinically meaningful observations (labs, vitals)
- Use timestamps to maintain rough chronological flow if possible

FILTERING:
- Ignore administrative or irrelevant observations
- Prioritize clinically meaningful data

STYLE:
- Write like a clinical case summary used in research datasets
- Use compact but detailed medical language
- Single paragraph

--------------------------------------------------

2) disease_list:

Extract a normalized list of clinically relevant diseases.

RULES:
- Include confirmed conditions/diagnoses
- Include chronic diseases
- Include major clinical findings
- Do NOT include minor symptoms
- Do NOT include procedures
- No duplicates
- Use normalized medical terms

--------------------------------------------------

Return STRICT JSON:

{
    "summary_text": "<detailed clinical summary>",
    "disease_list": ["Disease 1", "Disease 2"]
}

Return ONLY JSON.
"""

    response = client.chat.completions.create(
        model="gpt-3.5-turbo-0125",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(structured_json)},
        ],
        temperature=0,
        response_format={"type": "json_object"}
    )
    try:
        from services.ai_usage import emit_llm_usage

        emit_llm_usage(
            patient_id=str(patient_id) if patient_id else None,
            product="patient_summary",
            feature="patient_summary.mimic",
            provider="openai",
            model="gpt-3.5-turbo-0125",
            usage=response.usage,
            source_service="hekma-trialgpt",
        )
    except Exception:
        pass

    content = response.choices[0].message.content

    try:
        parsed = json.loads(content)

        return {
            "summary_text": parsed.get("summary_text", "").strip(),
            "disease_list": list(
                {str(d).strip() for d in parsed.get("disease_list", []) if d}
            )
        }

    except Exception:
        return {
            "summary_text": content.strip(),
            "disease_list": []
        }