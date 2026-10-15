import argparse
import json
import os
import re
import sys
import traceback

import psycopg
from anthropic import Anthropic
from dotenv import load_dotenv
from tqdm import tqdm

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.llm_config import resolve_compose_model

load_dotenv()

EXPECTED_KEYS = {
    "demographics",
    "allergies",
    "conditions",
    "procedures",
    "medications",
    "observations",
    "immunizations",
}
from datetime import date

current_date = date.today()

PROD_PROMPT = f"""You are a clinical summarization assistant.
Given patient data, return ONLY a valid JSON object with exactly these 7 keys:
- demographics
- allergies
- conditions
- procedures
- medications
- observations
- immunizations

Today's date is {current_date}. Use this to calculate patient age from date of birth if DOB is available in the patient data.
If DOB is not available but age is explicitly stated (e.g., "58-year-old" or "Age: 45"), use that directly.
If neither DOB nor explicit age is available, omit age from demographics.

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

Example format:
{{
  "demographics": "58-year-old female",
  "allergies": null,
  "conditions": "Type 2 diabetes, hypertension",
  "procedures": null,
  "medications": "Metformin, lisinopril",
  "observations": "Elevated HbA1c",
  "immunizations": null
}}
"""

SYSTEM_PROMPT = """You are a clinical summarization assistant.

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

Example format:
{
  "demographics": "58-year-old female", # only if age is explicitly stated; otherwise omit age
  "allergies": null,
  "conditions": "Type 2 diabetes, hypertension",
  "procedures": null,
  "medications": "Metformin, lisinopril",
  "observations": "Elevated HbA1c",
  "immunizations": null
}
"""


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max",
        type=int,
        default=1502,
        help="Max number of patients to process",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="patient_block_summaries_v2.json",
        help="Output JSON file",
    )
    return parser.parse_args()


def parse_model_json(response, patient_id):
    """Safely parse JSON from Anthropic response and validate required keys."""
    raw_text = "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text" and hasattr(block, "text")
    ).strip()

    print(f"[DEBUG] patient_id={patient_id}")
    print("[DEBUG] raw Claude output:")
    print(repr(raw_text))

    if not raw_text:
        raise ValueError(f"Empty response from Claude for patient_id={patient_id}")

    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
        raw_text = re.sub(r"\s*```$", "", raw_text).strip()
    raw_text = re.sub(r",\s*([}\]])", r"\1", raw_text)

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"(\{.*\}|\[.*\])", raw_text, re.DOTALL)
        if not match:
            raise ValueError(
                f"No JSON found in Claude response for patient_id={patient_id}\n"
                f"Output:\n{raw_text}"
            )

        candidate = match.group(1)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Invalid JSON for patient_id={patient_id}\n"
                f"Extracted candidate:\n{candidate}\n"
                f"Original output:\n{raw_text}\n"
                f"Parse error: {e}"
            ) from e

    if not isinstance(parsed, dict):
        raise ValueError(
            f"Expected JSON object for patient_id={patient_id}, got {type(parsed).__name__}"
        )

    parsed_keys = set(parsed.keys())
    if parsed_keys != EXPECTED_KEYS:
        raise ValueError(
            f"Unexpected JSON keys for patient_id={patient_id}. "
            f"Expected {EXPECTED_KEYS}, got {parsed_keys}"
        )

    for key in EXPECTED_KEYS:
        value = parsed[key]
        if value is not None and not isinstance(value, str):
            raise ValueError(
                f"Invalid value type for key '{key}' in patient_id={patient_id}. "
                f"Expected str or null, got {type(value).__name__}"
            )

    return parsed


def extract_summaries(client, patient_id, summary_text):
    """Call Claude and extract structured block summaries."""
    content = (
        f"Patient ID: {patient_id}\n\n"
        f"Patient Data:\n{summary_text}\n\n"
        "Return ONLY valid JSON. Do not include markdown fences or explanations."
    )

    response = client.messages.create(
        model=resolve_compose_model(None),
        max_tokens=1000,
        temperature=0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    return parse_model_json(response, patient_id)


def load_existing_results(output_path):
    """Load existing results to support resume."""
    if not os.path.exists(output_path):
        return {}

    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Existing output file must contain a JSON object: {output_path}")

    return data


def save_results(output_path, results):
    """Persist results after each patient for resumability."""
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def main():
    """Main entry point."""
    args = parse_args()

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    conn = psycopg.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5433")),
        dbname=os.getenv("PG_DB", "hekma_platform"),
        user=os.getenv("PG_USER", "hekma"),
        password=os.environ["PG_PASSWORD"],
    )

    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT patient_id, summary_text, structured_json "
                "FROM mimic_patient_summary "
                "LIMIT %s",
                (args.max,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    results = load_existing_results(args.output)

    for row in tqdm(rows, desc="Processing patients", unit="patient"):
        patient_id, summary_text, structured_json = row

        patient_id = str(patient_id)

        if patient_id in results:
            continue  # skip already processed

        try:
            summaries = extract_summaries(client, patient_id, summary_text)
            results[patient_id] = summaries
        except Exception as e:
            results[patient_id] = {"error": str(e)}
            print(traceback.format_exc())
            save_results(args.output, results)
            sys.exit(0)

        save_results(args.output, results)

    print(f"Done. {len(results)} patients saved to {args.output}")


if __name__ == "__main__":
    main()