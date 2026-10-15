import json
import argparse
from collections import defaultdict


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_sentence_indices(x):
    if x is None:
        return set()

    if isinstance(x, list):
        return set(int(i) for i in x if str(i).isdigit())

    if not isinstance(x, str):
        return set()

    x = x.strip()
    if x.lower() in ["", "none", "[]"]:
        return set()

    try:
        x = x.replace("'", '"')
        if not x.startswith("["):
            x = "[" + x + "]"
        parsed = json.loads(x)
        return set(int(i) for i in parsed)
    except Exception:
        cleaned = x.strip("[] ")
        if not cleaned:
            return set()
        return set(int(i.strip()) for i in cleaned.split(",") if i.strip().isdigit())


def main(gt_path, model_output_path):

    print("Loading gold dataset...")
    gt_records = load_json(gt_path)
    print(f"Loaded {len(gt_records)} gold criterion records.")

    print("Loading model outputs...")
    model_outputs = load_json(model_output_path)

    # Group GT by (patient_id, trial_id, criterion_type)
    grouped_gt = defaultdict(lambda: defaultdict(list))
    for record in gt_records:
        key = (record["patient_id"], record["trial_id"])
        grouped_gt[key][record["criterion_type"]].append(record)

    total_criteria = 0
    correct_eligibility = 0

    global_tp = 0
    global_fp = 0
    global_fn = 0

    for (patient_id, trial_id), type_map in grouped_gt.items():

        if patient_id not in model_outputs:
            continue

        # Model output has an extra case-index level: patient_id -> case_idx -> trial_id
        trial_pred = None
        for case_idx in model_outputs[patient_id].values():
            if trial_id in case_idx:
                trial_pred = case_idx[trial_id]
                break

        if trial_pred is None:
            continue

        for criterion_type, gt_list in type_map.items():

            if criterion_type not in trial_pred:
                continue

            pred_type_block = trial_pred[criterion_type]

            for idx, gt_record in enumerate(gt_list):

                idx_str = str(idx)

                if idx_str not in pred_type_block:
                    continue

                total_criteria += 1

                model_pred = pred_type_block[idx_str]

                if len(model_pred) < 3:
                    continue

                model_label = model_pred[2]
                model_sentences = model_pred[1]

                gold_label = gt_record["expert_eligibility"]
                gold_sentences = gt_record["expert_sentences"]

                # Eligibility
                if model_label == gold_label:
                    correct_eligibility += 1

                # Sentence evidence
                pred_set = parse_sentence_indices(model_sentences)
                gold_set = parse_sentence_indices(gold_sentences)

                tp = len(pred_set & gold_set)
                fp = len(pred_set - gold_set)
                fn = len(gold_set - pred_set)

                global_tp += tp
                global_fp += fp
                global_fn += fn

    # --- Final Metrics ---

    eligibility_accuracy = (
        correct_eligibility / total_criteria if total_criteria > 0 else 0.0
    )

    precision = (
        global_tp / (global_tp + global_fp)
        if (global_tp + global_fp) > 0
        else 0.0
    )

    recall = (
        global_tp / (global_tp + global_fn)
        if (global_tp + global_fn) > 0
        else 0.0
    )

    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    print("\n--- Micro-Averaged Results ---")
    print(f"Total Criteria Evaluated: {total_criteria}")
    print(f"Eligibility Accuracy: {eligibility_accuracy:.4f}")
    print(f"Sentence Precision:   {precision:.4f}")
    print(f"Sentence Recall:      {recall:.4f}")
    print(f"Sentence F1:          {f1:.4f}")
    print("--------------------------------")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate model outputs against ground truth.")
    parser.add_argument("--gt", required=True, help="Path to ground truth JSON file (flat list).")
    parser.add_argument("--pred", required=True, help="Path to model output JSON file.")
    args = parser.parse_args()

    main(args.gt, args.pred)
