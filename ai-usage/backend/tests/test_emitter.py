import sys
from pathlib import Path

from app.pricing import normalize_provider

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from hekma_ai_usage.client import parse_usage_payload


def test_provider_aliases():
    assert normalize_provider("claude") == "anthropic"
    assert normalize_provider("gemini") == "google"
    assert normalize_provider("azure_openai") == "openai"
    assert normalize_provider("GROQ") == "groq"


def test_parse_usage_from_each_provider_shape():
    assert parse_usage_payload({"prompt_tokens": 10, "completion_tokens": 4}) == (10, 4, 14)
    assert parse_usage_payload({"input_tokens": 10, "output_tokens": 4}) == (10, 4, 14)
    assert parse_usage_payload({"prompt_token_count": 10, "candidates_token_count": 4}) == (10, 4, 14)
