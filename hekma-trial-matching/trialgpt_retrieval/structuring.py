#!/usr/bin/env python3

"""
LLM Patient Structuring Script

Reads a JSONL file with patient descriptions and converts them into
structured clinical profiles using an LLM.

Input format (JSONL):
{"_id": "...", "text": "patient description"}

Output format (JSON):
{
    "patient_id": {
        structured patient profile
    }
}
"""

__author__ = "Danial"

import argparse
import json
import os
from typing import Dict, Any

from tqdm import tqdm
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY", "")
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable not set.")

client = OpenAI(api_key=api_key)

SYSTEM_PROMPT = """
You are a clinical information extraction system.

Your task is to convert a patient description into structured clinical data.

Rules:
1. Only extract information explicitly stated or strongly implied.
2. Do NOT invent diseases or symptoms.
3. If a field is unknown, return null or an empty list.
4. Use concise medical terminology.
5. Output MUST be valid JSON.

Return exactly this JSON schema:

{
  "summary": "short clinical summary",

  "demographics": {
    "age": number or null,
    "sex": "male | female | unknown"
  },

  "conditions": [],

  "symptoms": [],

  "risk_factors": [],

  "medical_history": [],

  "negated_conditions": [],

  "tests": []
}
"""


def extract_patient_structure(
    client: OpenAI,
    model: str,
    patient_text: str
) -> Dict[str, Any]:
    """
    Run LLM extraction for a single patient.
    """

    user_prompt = f"""
Patient description:

{patient_text}

Extract the structured information.
Return JSON only.
"""

    response = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.choices[0].message.content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # fallback if model wraps JSON
        start = content.find("{")
        end = content.rfind("}") + 1
        return json.loads(content[start:end])


def main(dataset_path: str, output_path: str, model: str):

    #client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    results = {}

    with open(dataset_path, "r") as f:
        lines = [json.loads(x) for x in f]

    for instance in tqdm(lines, desc="Structuring patients"):

        patient_id = instance["_id"]
        patient_text = instance["text"]

        structured = extract_patient_structure(
            client,
            model,
            patient_text
        )

        results[patient_id] = {
            "patient_note": patient_text,
            "patient_profile": structured
        }

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-dp",
        "--dataset_path",
        required=True,
        help="Path to JSONL patient dataset",
    )

    parser.add_argument(
        "-op",
        "--output_path",
        default="structured_patients.json",
        help="Output JSON file",
    )

    parser.add_argument(
        "-m",
        "--model",
        default="gpt-4o-mini",
        help="LLM model name",
    )

    args = parser.parse_args()

    main(
        args.dataset_path,
        args.output_path,
        args.model,
    )