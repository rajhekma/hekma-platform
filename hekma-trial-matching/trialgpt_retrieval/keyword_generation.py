__author__ = "qiao"
"""
generate the search keywords for each patient
"""
from dotenv import load_dotenv
load_dotenv()
import json
import os
import argparse

from utils.anthropic_messages import create_anthropic_message
from services.ai_usage import current_usage_patient_id, emit_llm_usage


def build_client(llm_service):
    if llm_service == "openai":
        from openai import OpenAI, AzureOpenAI
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key.startswith("sk-"):
            return OpenAI(api_key=api_key)
        else:
            return AzureOpenAI(
                api_version="2023-09-01-preview",
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("OPENAI_ENDPOINT"),
                api_key=os.getenv("AZURE_OPENAI_API_KEY") or api_key,
            )
    elif llm_service == "gemini":
        from google import genai
        return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    elif llm_service == "claude":
        import anthropic
        return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    else:
        raise ValueError(f"Unsupported LLM service: {llm_service}")


def get_keyword_generation_messages(note):
	system = 'You are a helpful assistant and your task is to help search relevant clinical trials for a given patient description. Please first summarize the main medical problems of the patient. Then generate up to 32 key conditions for searching relevant clinical trials for this patient. The key condition list should be ranked by priority. Please output only a JSON dict formatted as Dict{{"summary": Str(summary), "conditions": List[Str(condition)]}}.'

	prompt =  f"Here is the patient description: \n{note}\n\nJSON output:"

	messages = [
		{"role": "system", "content": system},
		{"role": "user", "content": prompt}
	]
	
	return messages

# def get_keyword_generation_messages(note):
#     """
#     Prepare the messages for keyword generation based on a patient note.

#     Args:
#         note (str): The patient description.

#     Returns:
#         list: A list of message dictionaries for the AI model.
#     """
#     system = """You are a medical research assistant specializing in clinical trial matching. Your task is to analyze patient descriptions to identify key medical conditions and assist in finding suitable clinical trials. Prioritize accuracy and relevance in your analysis."""

#     prompt = f"""Please analyze the following patient description for clinical trial matching:

#     ## {note}

#     ### Instructions:
#     1. Summarize the patient's main medical issues in 3-5 sentences.
#     2. List up to 32 key medical conditions, ranked by relevance for clinical trial matching.
#     3. Use standardized medical terminology (e.g., "Type 2 Diabetes" instead of "high blood sugar").
#     4. Include conditions only if explicitly mentioned or strongly implied in the description.

#     ### Output a JSON object in this format:
#     **Provide ONLY a valid JSON object** with the following structure:
#     {{
#       "summary": "Brief patient summary",
#       "conditions": ["Condition 1", "Condition 2", ...]
#     }}

#     ### Important Notes:
#     - If you are unsure about a condition, include it only if it is explicitly mentioned or strongly implied in the description.
#     - **Do NOT include any text outside of the JSON object.** This means no notes, explanations, headers, or footers outside the JSON.

#     Now, please process the patient description and respond with the JSON object.
#     """

#     return [
#         {"role": "system", "content": system},
#         {"role": "user", "content": prompt}
    # ]

def call_llm(client, llm_service, messages, model):
    """Returns (text, input_tokens, output_tokens)"""
    if llm_service == "openai":
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
        )
        usage = response.usage
        return response.choices[0].message.content, usage.prompt_tokens, usage.completion_tokens

    elif llm_service == "gemini":
        from google.genai import types
        system = messages[0]["content"]
        user = messages[1]["content"]
        response = client.models.generate_content(
            model=model,
            config=types.GenerateContentConfig(system_instruction=system, temperature=0),
            contents=user,
        )
        usage = response.usage_metadata
        return response.text, usage.prompt_token_count, usage.candidates_token_count

    elif llm_service == "claude":
        system = messages[0]["content"]
        user_messages = [{"role": m["role"], "content": m["content"]} for m in messages[1:]]
        response = create_anthropic_message(
            client,
            model=model,
            max_tokens=1024,
            temperature=0,
            system=system,
            messages=user_messages,
        )
        usage = response.usage
        return response.content[0].text, usage.input_tokens, usage.output_tokens


def parse_output(raw):
    output = raw.strip("`").strip("json").strip()
    return json.loads(output)


def generate_keywords(input_path, output_path, model, llm_service="openai", client=None):
    if client is None:
        client = build_client(llm_service)
    outputs = {}
    total_input_tokens = 0
    total_output_tokens = 0

    with open(input_path, "r") as f:
        for line in f.readlines():
            entry = json.loads(line)
            messages = get_keyword_generation_messages(entry["text"])
            raw, input_tokens, output_tokens = call_llm(client, llm_service, messages, model)
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            print(f"[{entry['_id']}] input={input_tokens}, output={output_tokens}")
            outputs[entry["_id"]] = parse_output(raw)
            with open(output_path, "w") as out_f:
                json.dump(outputs, out_f, indent=4)

    print(f"\nTotal input tokens : {total_input_tokens}")
    print(f"Total output tokens: {total_output_tokens}")
    print(f"Total tokens       : {total_input_tokens + total_output_tokens}")


def generate_keywords_for_text(text, model, llm_service="openai", client=None):
    if client is None:
        client = build_client(llm_service)
    messages = get_keyword_generation_messages(text)
    raw, input_tokens, output_tokens = call_llm(client, llm_service, messages, model)
    print(f"input={input_tokens}, output={output_tokens}, total={input_tokens + output_tokens}")
    emit_llm_usage(
        patient_id=current_usage_patient_id(),
        product="trial_match",
        feature="trial_match.keywords",
        provider=llm_service,
        model=model,
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        source_service="hekma-trialgpt",
    )
    return parse_output(raw)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate search keywords for patients.")
    parser.add_argument("corpus", type=str, help="Corpus name: trec_2021, trec_2022, or sigir")
    parser.add_argument("model", type=str, help="Model name to use")
    parser.add_argument(
        "--llm-service",
        type=str,
        default="openai",
        choices=["openai", "gemini", "claude"],
        help="LLM service to use (default: openai)"
    )
    parser.add_argument(
        "--input-path",
        type=str,
        default=None,
        help="Override default input path"
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=None,
        help="Override default output path"
    )

    args = parser.parse_args()

    input_path = "/home/mayu/Documents/Code/HEKMA/trailgpt_default/common_everything/queries_filtered.jsonl"#args.input_path or f"dataset/{args.corpus}/queries.jsonl"
    output_path = f"{args.output_path}/retrieval_keywords_{args.model}_{args.corpus}.json" or f"results_gpt5/retrieval_keywords_{args.model}_{args.corpus}.json"

    client = build_client(args.llm_service)
    generate_keywords(input_path, output_path, args.model, args.llm_service, client)