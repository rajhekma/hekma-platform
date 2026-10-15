import json
import os
from collections import defaultdict
from openai import OpenAI
from utils.pg_util import pg_transaction

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

TARGET_PER_CATEGORY = 80
BATCH_SIZE_LLM = 10
MAX_DISEASE_REPEAT = 10   

CATEGORIES = [
    "Oncology",
    "Cardiology",
    "Diabetes / Metabolic",
    "Respiratory",
    "Neurology"
]

client = OpenAI(api_key=OPENAI_API_KEY)

disease_counter = defaultdict(int)


# =============== CLEANING FUNCTION ===============
def clean_conditions(conditions):
    cleaned = []

    for c in conditions:
        c_lower = c.lower()

        #  remove noise
        if "entered in error" in c_lower:
            continue

        if any(x in c_lower for x in [
            "employment", "education", "social", "violence",
            "transport", "criminal", "housing"
        ]):
            continue

        # diversity filter
        if disease_counter[c_lower] >= MAX_DISEASE_REPEAT:
            continue

        cleaned.append(c.strip())

    # remove duplicates + reduce token size
    return list(set(cleaned))[:10]


# =============== LLM (STRICT + DIVERSE + CHEAP) ===============
def classify_batch_with_llm(batch_inputs):

    formatted = ""
    for i, (_, diseases) in enumerate(batch_inputs):
        formatted += f"{i+1}. {diseases}\n"

    prompt = f"""
You are a clinical classification system.

Task:
Assign EXACTLY ONE category per patient OR NONE.

Categories:
- Oncology
- Cardiology
- Diabetes / Metabolic
- Respiratory
- Neurology

Rules:

1. Consider ONLY confirmed diseases.
   Ignore symptoms, social factors, and non-clinical entries.

2. Identify the PRIMARY disease:
   - based on the main organ system affected
   - not based on frequency or commonness

3. Do NOT accept weak signals:
   - hypertension alone → NONE
   - prediabetes alone → NONE
   - hyperglycemia alone → NONE

4. Use clinical reasoning:
   - organ-specific disease overrides general conditions
   - example: nerve disorder overrides diabetes
   - example: brain disorder overrides hypertension

5. Ensure diversity:
   - avoid repeating same disease patterns
   - prefer varied disease types within a category

6. If unclear or mixed → return NONE

Output:
1. Category
2. Category
3. NONE

Patients:
{formatted}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        timeout=15
    )

    lines = response.choices[0].message.content.strip().split("\n")

    results = []
    for line in lines:
        if "." in line:
            results.append(line.split(".", 1)[1].strip())
        else:
            results.append(line.strip())

    return results


# =============== MAIN LOGIC ===============
def get_400_patients():

    patient_conditions = defaultdict(list)
    category_pool = defaultdict(set)
    cache = {}

    offset = 0
    batch_size = 5000

    with pg_transaction() as (conn, cursor):

        while True:

            cursor.execute(f"""
                SELECT 
                    patient_id,
                    raw_resource->'code'->>'text' AS condition_text
                FROM condition
                WHERE raw_resource IS NOT NULL
                AND raw_resource->'code'->>'text' IS NOT NULL
                OFFSET {offset}
                LIMIT {batch_size};
            """)

            rows = cursor.fetchall()

            if not rows:
                break

            print(f"\nProcessing batch OFFSET {offset} (rows={len(rows)})")

            # ===== BUILD DATA + UPDATE COUNTER =====
            for row in rows:
                patient_id = row["patient_id"]
                condition_text = row["condition_text"]

                if not condition_text:
                    continue

                #update global frequency
                disease_counter[condition_text.lower()] += 1

                patient_conditions[patient_id].append(condition_text)

            # ===== CLASSIFICATION =====
            batch = []

            for patient_id, conditions in patient_conditions.items():

                # avoid overlap
                already_assigned = any(
                    patient_id == pid
                    for c in CATEGORIES
                    for (pid, _) in category_pool[c]
                )
                if already_assigned:
                    continue

                cleaned_conditions = clean_conditions(conditions)

                if not cleaned_conditions:
                    continue

                diseases_str = ", ".join(cleaned_conditions)
                key = diseases_str.lower()

                # cache
                if key in cache:
                    category = cache[key]

                    if category in CATEGORIES:
                        category_pool[category].add((patient_id, diseases_str))

                    continue

                batch.append((patient_id, diseases_str, key))

                # ===== BATCH CALL =====
                if len(batch) >= BATCH_SIZE_LLM:

                    try:
                        llm_inputs = [(pid, diseases) for (pid, diseases, _) in batch]
                        results = classify_batch_with_llm(llm_inputs)

                        for (pid, diseases, key), category in zip(batch, results):

                            cache[key] = category

                            if category in CATEGORIES:
                                category_pool[category].add((pid, diseases))
                                print(f"Added {pid} → {category}")

                    except Exception as e:
                        print("Batch error:", e)

                    batch = []

            # ===== FINAL REMAINING BATCH =====
            if batch:
                try:
                    llm_inputs = [(pid, diseases) for (pid, diseases, _) in batch]
                    results = classify_batch_with_llm(llm_inputs)

                    for (pid, diseases, key), category in zip(batch, results):

                        cache[key] = category

                        if category in CATEGORIES:
                            category_pool[category].add((pid, diseases))
                            print(f"Added {pid} → {category}")

                except Exception as e:
                    print("Final batch error:", e)

            # stop early if done
            if all(len(category_pool[c]) >= TARGET_PER_CATEGORY for c in CATEGORIES):
                print(" All categories reached target")
                break

            offset += batch_size

    # ===== FINAL OUTPUT =====
    category_patients = {}

    for category in CATEGORIES:
        patients_with_data = list(category_pool.get(category, []))
        print(f"{category} available: {len(patients_with_data)}")
        category_patients[category] = patients_with_data[:TARGET_PER_CATEGORY]

    return category_patients


# =============== SAVE ===============
def save_to_file(category_patients):
    with open("condition_selected_patients.txt", "w") as f:
        total = 0

        for category in CATEGORIES:
            patients = category_patients.get(category, [])

            f.write(f"=== {category} ({len(patients)}) ===\n")

            for (pid, diseases) in patients:
                f.write(f"{pid} | {diseases}\n")
                total += 1

            f.write("\n")

        f.write(f"\nTOTAL PATIENTS: {total}\n")

    print("Saved to condition_selected_patients.txt")


# =============== RUN ===============
if __name__ == "__main__":
    result = get_400_patients()
    save_to_file(result)