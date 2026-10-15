from repositories.patient_annotation_repo import (
    insert_patient,
    get_all_patients,
    get_patient as repo_get_patient,
    update_comments as repo_update_comments
)
from uuid import uuid4
import copy


def upload_patient(data):
    # -------- normalize input --------
    if isinstance(data, list):
        # handle nested list case [[...]]
        if len(data) == 1 and isinstance(data[0], list):
            data = data[0]

    # -------- CASE 1: Single patient --------
    if isinstance(data, dict):
        pid = data.get("Patient_ID", str(uuid4()))
        insert_patient(pid, data)

        return {
            "type": "single",
            "id": pid
        }

    # -------- CASE 2: Bulk patients --------
    elif isinstance(data, list):
        count = 0
        ids = []

        for patient in data:
            if not isinstance(patient, dict):
                raise Exception("Each patient must be a dictionary")

            pid = patient.get("Patient_ID", str(uuid4()))
            insert_patient(pid, patient)
            ids.append(pid)
            count += 1

        return {
            "type": "bulk",
            "uploaded": count,
            "ids": ids
        }

    else:
        raise Exception("Invalid data format")    


def list_patients():
    rows = get_all_patients()

    return [
        {
            "id": r["patient_id"],
            "summary": r.get("summary") or "",
            "has_review_requests": r["has_review_requests"],
            "is_commented": bool(r.get("is_commented")),
        }
        for r in rows
    ]

def get_patient(pid):
    row = repo_get_patient(pid)
    if not row:
        raise Exception("Not found")

    return {
        "data": row["data"],
        "comments": row["comments"]
    }


def update_comments(pid, payload):
    row = repo_get_patient(pid)
    if not row:
        raise Exception("Not found")

    comments = row["comments"] or {"Trials": []}

    trial = _find_or_create_trial(comments, payload["trial_index"])

    # reset to draft
    for f in payload["fields"]:
        if "status" not in payload["fields"][f]:
            payload["fields"][f]["status"] = "draft"

    if payload["type"] == "trial_fields":
        trial["trial_fields"].update(payload["fields"])

    else:
        item = _find_or_create_item(
            trial[payload["type"]],
            payload["item_index"]
        )
        item["fields"].update(payload["fields"])

    has_review = _compute_review_flag(comments)

    repo_update_comments(pid, comments, has_review)

    return {"status": "updated"}


def get_final_json(pid):
    row = repo_get_patient(pid)
    if not row:
        raise Exception("Not found")

    data = copy.deepcopy(row["data"])
    comments = row["comments"]

    for t_index, trial in enumerate(data.get("Trials", [])):
        t_comment = _get_trial(comments, t_index)

        for field in ["Relevance_Reasoning", "Eligibility_Reasoning", "Predicted_Labels"]:
            if field in t_comment.get("trial_fields", {}):
                trial[f"{field}_comments"] = t_comment["trial_fields"][field]["comment"]

        for i, item in enumerate(trial.get("Matching_Results", {}).get("inclusion", [])):
            ic = _get_item(t_comment, "inclusion", i)

            if "LLM_output" in ic:
                item["LLM_output_comments"] = ic["LLM_output"]["comment"]

        for i, item in enumerate(trial.get("Matching_Results", {}).get("exclusion", [])):
            ec = _get_item(t_comment, "exclusion", i)

            if "LLM_output" in ec:
                item["LLM_output_comments"] = ec["LLM_output"]["comment"]

    return data


# -------- helpers --------

def _find_or_create_trial(comments, idx):
    for t in comments["Trials"]:
        if t["trial_index"] == idx:
            return t

    t = {
        "trial_index": idx,
        "trial_fields": {},
        "inclusion": [],
        "exclusion": []
    }
    comments["Trials"].append(t)
    return t


def _find_or_create_item(section, idx):
    for i in section:
        if i["item_index"] == idx:
            return i

    i = {"item_index": idx, "fields": {}}
    section.append(i)
    return i


def _compute_review_flag(comments):
    for t in comments.get("Trials", []):
        for f in t.get("trial_fields", {}).values():
            if f.get("status") == "needs_review":
                return True

        for sec in ["inclusion", "exclusion"]:
            for item in t.get(sec, []):
                for f in item.get("fields", {}).values():
                    if f.get("status") == "needs_review":
                        return True

    return False


def _get_trial(comments, idx):
    for t in comments.get("Trials", []):
        if t["trial_index"] == idx:
            return t
    return {}


def _get_item(trial, sec, idx):
    for i in trial.get(sec, []):
        if i["item_index"] == idx:
            return i.get("fields", {})
    return {}