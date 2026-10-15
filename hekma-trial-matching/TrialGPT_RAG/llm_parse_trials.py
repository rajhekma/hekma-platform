import argparse
import json
import os
import re
import sys
import traceback

from anthropic import Anthropic
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
_DEFAULT_INPUT = os.path.join(_REPO_ROOT, "dataset", "corpus_annot_10.jsonl")
_DEFAULT_OUTPUT = os.path.join(_REPO_ROOT, "dataset", "trials.jsonl")
# PDF says "claude-sonnet-4"; Anthropic API uses a dated snapshot id:
_DEFAULT_MODEL = os.getenv("BLOCK_STRUCTURE_MODEL", "claude-sonnet-4-20250514")

CRITERIA_SYSTEM_PROMPT = """You are a clinical trial criteria parser.

Given raw inclusion or exclusion criteria text, return ONLY a valid JSON object.
Each key is a criterion number as a string, and each value is the criterion text.

Rules:
1. Output must be a single valid JSON object.
2. Do not include markdown fences or explanations.
3. Each criterion must be a standalone, self-contained entry.
4. Sub-items (e.g., i), ii), a), b)) that belong to a parent criterion must be merged into that parent entry as a single text block — do not split them into separate entries.
5. Remove any header lines like "Inclusion criteria:", "Exclusion criteria:", or lone colons.
6. Preserve all clinical detail exactly — do not paraphrase or summarize.
7. Numbering must be sequential starting from 1.

Example output:
{
  "1": "Age > 18 years at the time of signing the informed consent form",
  "2": "Present with active disease with at least one of the following: i) Arthritis ii) Skin rash iii) Oral ulcers",
  "3": "Hemoglobin >= 100 g/L"
}
"""


def parse_criteria_with_claude(client, criteria_text, criteria_type, model: str):
    """Use Claude to parse and structure criteria text."""
    if not criteria_text or not criteria_text.strip():
        return {}

    response = client.messages.create(
        model=model,
        max_tokens=2000,
        temperature=0,
        system=CRITERIA_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Parse the following {criteria_type} criteria:\n\n{criteria_text}",
            }
        ],
    )

    raw = "".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text" and hasattr(block, "text")
    ).strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw).strip()

    parsed = json.loads(raw)

    if not isinstance(parsed, dict):
        raise ValueError(f"Expected JSON object for {criteria_type} criteria, got {type(parsed).__name__}")

    for key, value in parsed.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError(f"Invalid criterion entry: {key}: {value}")

    return parsed


def process_trial(client, trial, model: str):
    """Extract metadata and parse criteria for a single trial."""
    metadata = trial.get("metadata", {})

    inclusion_raw = metadata.get("inclusion_criteria", "")
    exclusion_raw = metadata.get("exclusion_criteria", "")

    inclusion_parsed = parse_criteria_with_claude(client, inclusion_raw, "inclusion", model)
    exclusion_parsed = parse_criteria_with_claude(client, exclusion_raw, "exclusion", model)

    return {
        "nct_id": trial.get("_id", ""),
        "brief_title": metadata.get("brief_title", ""),
        "phase": metadata.get("phase", ""),
        "drugs": metadata.get("drugs_list", []),
        "diseases": metadata.get("diseases_list", []),
        "enrollment": metadata.get("enrollment", None),
        "brief_summary": metadata.get("brief_summary", ""),
        "inclusion_criteria": inclusion_parsed,
        "exclusion_criteria": exclusion_parsed,
    }


def load_existing_results(output_path):
    """Load successfully parsed NCT IDs for resumability (skip error rows)."""
    results = {}
    if not os.path.exists(output_path):
        return results
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("error"):
                continue
            if record.get("inclusion_criteria") is not None:
                results[record["nct_id"]] = True
    return results


def main():
    parser = argparse.ArgumentParser(description="Parse trial inclusion/exclusion criteria with Claude.")
    parser.add_argument(
        "-i", "--input",
        default=_DEFAULT_INPUT,
        help=f"Raw corpus JSONL (default: {_DEFAULT_INPUT})",
    )
    parser.add_argument(
        "-o", "--output",
        default=_DEFAULT_OUTPUT,
        help=f"Parsed trials JSONL output (default: {_DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "-m", "--model",
        default=_DEFAULT_MODEL,
        help=f"Anthropic model (default: {_DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete existing output file before running (re-parse all trials)",
    )
    args = parser.parse_args()
    input_path = args.input
    output_path = args.output
    model = args.model

    if not os.path.exists(input_path):
        print(f"Input file not found: {input_path}")
        sys.exit(1)

    if args.fresh and os.path.exists(output_path):
        os.remove(output_path)
        print(f"Removed existing output: {output_path}")

    client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    with open(input_path, "r", encoding="utf-8") as f:
        trials = [json.loads(line) for line in f if line.strip()]

    processed = load_existing_results(output_path)
    print(f"Resuming: {len(processed)} already processed.")

    out_file = open(output_path, "a", encoding="utf-8")

    try:
        for trial in tqdm(trials, desc="Parsing trials", unit="trial"):
            nct_id = str(trial.get("_id", ""))

            if nct_id in processed:
                continue

            try:
                result = process_trial(client, trial, model)
                out_file.write(json.dumps(result, ensure_ascii=False) + "\n")
                out_file.flush()
            except Exception as e:
                error_record = {"nct_id": nct_id, "error": str(e)}
                out_file.write(json.dumps(error_record, ensure_ascii=False) + "\n")
                out_file.flush()
                print(traceback.format_exc())

    finally:
        out_file.close()

    print(f"Done. Output saved to {output_path}")


if __name__ == "__main__":
    main()