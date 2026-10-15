import os
import json
import requests

from services.criteria_parser import parse_eligibility_criteria
from services.trial_llm_service import generate_trial_corpus_object
from repositories.trialgpt_corpus_repo import upsert_trial_corpus

import logging

logger = logging.getLogger("trial_ingestion")
logging.basicConfig(level=logging.INFO)


CLINICAL_API = "https://clinicaltrials.gov/api/v2/studies/{}?format=json&markupFormat=legacy"


def fetch_trial_from_clinical_gov(nct_id: str):
    response = requests.get(
        CLINICAL_API.format(nct_id),
        headers={"accept": "application/json"}
    )

    logger.info(f"Fetching trial from ClinicalTrials API: {nct_id}")

    if response.status_code != 200:
        logger.error(f"ClinicalTrials API failed for {nct_id}")
        raise Exception(f"ClinicalTrials API failed for {nct_id}")
    
    return response.json()


def ingest_single_nct(nct_id: str):

    body = fetch_trial_from_clinical_gov(nct_id)

    protocol = body.get("protocolSection", {})

    # --- Title ---
    ident = protocol.get("identificationModule", {})
    title = ident.get("officialTitle") or ident.get("briefTitle")

    # --- Eligibility ---
    elig = protocol.get("eligibilityModule", {})
    criteria_text = elig.get("eligibilityCriteria")

    if not criteria_text:
        raise Exception(f"No eligibility criteria found for {nct_id}")

    inclusion, exclusion = parse_eligibility_criteria(criteria_text)

    logger.info(f"Calling LLM to normalize trial: {nct_id}")
    llm_output = generate_trial_corpus_object(title, inclusion, exclusion)
    logger.info(f"LLM normalization completed for: {nct_id}")

    corpus_obj = json.loads(llm_output)

    corpus_obj["nct_id"] = nct_id
    corpus_obj["source_type"] = "nct"

    return upsert_trial_corpus(corpus_obj)

def ingest_bulk_list(nct_ids: list):

    results = []

    for nct_id in list(set(nct_ids)):

        if not nct_id.startswith("NCT"):
            results.append({"nct_id": nct_id, "status": "invalid_format"})
            continue

        try:
            result = ingest_single_nct(nct_id)
            results.append(result)
        except Exception as e:
            logger.error(f"Ingestion failed for {nct_id}: {str(e)}")
            results.append({"nct_id": nct_id, "status": "failed", "error": str(e)})
    
    logger.info(f"Bulk ingestion completed. Total processed: {len(results)}")
    return {"total": len(results), "results": results}




def extract_from_file(file_path: str):

    if not os.path.exists(file_path):
        raise Exception("File not found")

    with open(file_path, "r") as f:
        lines = f.readlines()

    nct_ids = [l.strip() for l in lines if l.strip()]

    if len(nct_ids) > 200:
        raise Exception("Max 200 NCTIDs allowed")

    return nct_ids


def ingest_manual(payload: dict):

    title = payload.get("title", "Manual Trial")
    inclusion = payload.get("inclusion", [])
    exclusion = payload.get("exclusion", [])

    llm_output = generate_trial_corpus_object(title, inclusion, exclusion)

    corpus_obj = json.loads(llm_output)

    corpus_obj["nct_id"] = None
    corpus_obj["source_type"] = "manual"

    return upsert_trial_corpus(corpus_obj)


def ingest_trials(payload: dict):


    input_type = payload.get("type")
    logger.info(f"Ingestion started. Type: {input_type}")


    if input_type == "nct":
        return ingest_single_nct(payload["nct_id"])

    elif input_type == "bulk_nct":
        return ingest_bulk_list(payload["nct_ids"])

    elif input_type == "bulk_file":
        nct_ids = extract_from_file(payload["file_path"])
        return ingest_bulk_list(nct_ids)

    elif input_type == "manual":
        return ingest_manual(payload)

    else:
        raise Exception("Invalid type")