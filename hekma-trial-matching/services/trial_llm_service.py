import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_trial_corpus_object(title, inclusion, exclusion):
    """
    Generates structured corpus-ready trial object.
    Deterministic JSON output.
    """

    system_prompt = """
    You are a clinical trial documentation assistant.
    Using the provided title, inclusion and exclusion lists,
    generate a structured JSON response with:
    - title
    - text (summary + formatted inclusion + formatted exclusion)
    - brief_summary
    - inclusion_criteria (array)
    - exclusion_criteria (array)

    Do not fabricate information.
    Return valid JSON only.
    """

    user_content = {
        "title": title,
        "inclusion": inclusion,
        "exclusion": exclusion
    }

    response = client.chat.completions.create(
        model="gpt-4-turbo",
        temperature=0,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": str(user_content)},
        ],
    )

    return response.choices[0].message.content.strip()