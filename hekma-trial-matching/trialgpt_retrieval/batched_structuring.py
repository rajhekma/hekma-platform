#!/usr/bin/env python3

"""
High-throughput LLM patient structuring.

Features
--------
- Batch inference
- Parallel API requests
- Retry handling
- tqdm progress bar
- Strict JSON schema extraction

Input JSONL:
{"_id": "...", "text": "patient description"}

Output JSON:
{
  patient_id: {
      "patient_note": "...",
      "patient_profile": {...}
  }
}
"""

__author__ = "Danial"

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any

from tqdm import tqdm
from openai import OpenAI


SYSTEM_PROMPT = """
You are a clinical information extraction system.

Convert each patient description into structured clinical data.

Rules:
- Only extract information explicitly stated or strongly implied.
- Never invent diseases.
- If unknown return null or empty list.
- Use concise medical terminology.

Return JSON using this schema for EACH patient:

{
  "summary": "",
  "demographics": {
    "age": null,
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


def build_batch_prompt(batch: List[Dict]) -> str:
    """
    Create prompt for multiple patients.
    """

    text = "Extract structured data for each patient.\n\n"

    for p in batch:
        text += f"Patient ID: {p['_id']}\n"
        text += f"Description: {p['text']}\n\n"

    text += """
Return JSON mapping patient_id -> structured profile.

Example:

{
 "patient_id": {...},
 "patient_id2": {...}
}
"""

    return text


def call_llm(client: OpenAI, model: str, prompt: str, retries: int = 3):

    for attempt in range(retries):

        try:

            response = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            )

            text = response.choices[0].message.content.strip()

            start = text.find("{")
            end = text.rfind("}") + 1

            return json.loads(text[start:end])

        except Exception:

            if attempt == retries - 1:
                raise

            time.sleep(2)


def process_batch(client, model, batch):

    prompt = build_batch_prompt(batch)

    structured = call_llm(client, model, prompt)

    results = {}

    for patient in batch:

        pid = patient["_id"]

        results[pid] = {
            "patient_note": patient["text"],
            "patient_profile": structured.get(pid, {}),
        }

    return results


def chunk_list(data, size):

    for i in range(0, len(data), size):
        yield data[i:i + size]


def main(dataset_path, output_path, model, batch_size, workers):

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    patients = []

    with open(dataset_path) as f:
        for line in f:
            patients.append(json.loads(line))

    batches = list(chunk_list(patients, batch_size))

    results = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:

        futures = [
            executor.submit(process_batch, client, model, batch)
            for batch in batches
        ]

        for future in tqdm(as_completed(futures), total=len(futures), desc="Processing"):

            batch_result = future.result()
            results.update(batch_result)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-dp",
        "--dataset_path",
        required=True,
        help="Input JSONL dataset"
    )

    parser.add_argument(
        "-op",
        "--output_path",
        default="structured_patients.json",
        help="Output JSON file"
    )

    parser.add_argument(
        "-m",
        "--model",
        default="gpt-4o-mini",
        help="LLM model"
    )

    parser.add_argument(
        "-bs",
        "--batch_size",
        type=int,
        default=5,
        help="Patients per request"
    )

    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=4,
        help="Parallel workers"
    )

    args = parser.parse_args()

    main(
        args.dataset_path,
        args.output_path,
        args.model,
        args.batch_size,
        args.workers,
    )