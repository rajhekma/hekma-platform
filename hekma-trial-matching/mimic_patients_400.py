import json
import os
from collections import defaultdict
from openai import OpenAI
from utils.pg_util import pg_transaction

# ================= CONFIG =================
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

TARGET_TOTAL = 400
TARGET_PER_CATEGORY = 80

CATEGORIES = [
    "Oncology",
    "Cardiology",
    "Diabetes / Metabolic",
    "Respiratory",
    "Neurology"
]

client = OpenAI(api_key=OPENAI_API_KEY)

# =============== LLM FUNCTION ===============
def classify_with_llm(diseases):
    prompt = f"""
You are a strict medical classifier.

Task:
Assign EXACTLY ONE category from the list below ONLY if there is a CLEAR and DIRECT match.

Allowed categories:
- Oncology
- Cardiology
- Diabetes / Metabolic
- Respiratory
- Neurology

Rules:
1. Only classify if a disease CLEARLY belongs to one of these categories.
2. DO NOT infer or guess.
3. DO NOT generalize (e.g., mental health ≠ neurology).
4. If none of the diseases match EXACTLY → return "NONE".
5. Return ONLY the category name or "NONE".

Diseases:
{diseases}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return response.choices[0].message.content.strip()

# =============== MAIN LOGIC ===============
def get_400_patients():
    category_patients = defaultdict(list)
    selected_patients = set()
    cache = {}

    with pg_transaction() as (conn, cursor):

        cursor.execute("""
            SELECT patient_id, disease_list
            FROM mimic_patient_summary
            WHERE disease_list IS NOT NULL
            ORDER BY RANDOM()
        """)

        rows = cursor.fetchall()

        for row in rows:

            if len(selected_patients) >= TARGET_TOTAL:
                break

            patient_id = row["patient_id"]
            disease_json = row["disease_list"]

            if patient_id in selected_patients:
                continue

            # parse disease list
            diseases = disease_json if isinstance(disease_json, list) else json.loads(disease_json)

            # caching key
            key = tuple(sorted([d.lower() for d in diseases]))

            try:
                if key in cache:
                    category = cache[key]
                else:
                    category = classify_with_llm(diseases)
                    cache[key] = category

                if category not in CATEGORIES:
                    continue

                if len(category_patients[category]) >= TARGET_PER_CATEGORY:
                    continue

                category_patients[category].append(patient_id)
                selected_patients.add(patient_id)

                print(f"Added {patient_id} → {category}")

            except Exception as e:
                print(f"Error for {patient_id}: {e}")
                continue

    return category_patients


# =============== SAVE OUTPUT ===============
def save_to_file(category_patients):
    with open("selected_patients.txt", "w") as f:
        total = 0

        for category in CATEGORIES:
            patients = category_patients.get(category, [])

            f.write(f"=== {category} ({len(patients)}) ===\n")

            for pid in patients:
                f.write(f"{pid}\n")
                total += 1

            f.write("\n")

        f.write(f"\nTOTAL PATIENTS: {total}\n")

    print("✅ Saved to selected_patients.txt")


# =============== RUN ===============
if __name__ == "__main__":
    result = get_400_patients()
    save_to_file(result)