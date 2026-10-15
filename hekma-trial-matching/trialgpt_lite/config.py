"""
Configuration settings for TrialGPT Lite.
Loads configurations from environment variables or standard project .env file.
"""

import os
from pathlib import Path

# Try loading from project root .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    root_env = Path(__file__).resolve().parent.parent / ".env"
    if root_env.exists():
        load_dotenv(root_env)
    else:
        load_dotenv()
except ImportError:
    pass

# ClinicalTrials.gov API v2 Settings
CTGOV_API_BASE_URL: str = os.getenv("CTGOV_API_BASE_URL", "https://clinicaltrials.gov/api/v2")
DEFAULT_PAGE_SIZE: int = int(os.getenv("CTGOV_DEFAULT_PAGE_SIZE", "20"))
MAX_PAGE_SIZE: int = int(os.getenv("CTGOV_MAX_PAGE_SIZE", "100"))
REQUEST_TIMEOUT_SECONDS: float = float(os.getenv("CTGOV_TIMEOUT_SECONDS", "15.0"))
MAX_RETRIES: int = int(os.getenv("CTGOV_MAX_RETRIES", "4"))
RETRY_BACKOFF_FACTOR: float = float(os.getenv("CTGOV_BACKOFF_FACTOR", "1.5"))

# Matching Engine Settings (100% Offline Rule-Based, Zero API Keys)
MATCHING_ENGINE: str = "heuristic"
MAX_STUDIES_FOR_EVALUATION: int = int(os.getenv("TRIALGPT_MAX_STUDIES_EVAL", "5"))
DEFAULT_RECRUITMENT_STATUSES: list[str] = ["RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"]

# PostgreSQL Cache Settings (Cache-Aside Pattern - 30 Days Storage)
PG_HOST: str = os.getenv("PG_HOST", "localhost")
PG_PORT: int = int(os.getenv("PG_PORT", "5433"))
PG_DB: str = os.getenv("PG_DB", "hekma_platform")
PG_USER: str = os.getenv("PG_USER", "hekma")
PG_PASSWORD: str = os.getenv("PG_PASSWORD", "")
PG_CACHE_ENABLED: bool = os.getenv("PG_CACHE_ENABLED", "true").lower() in ("true", "1", "yes")

# 30-Day Retention TTLs (30 days = 2,592,000 seconds)
CACHE_RETENTION_DAYS: int = int(os.getenv("CACHE_RETENTION_DAYS", "30"))
PG_CACHE_QUERY_TTL: int = int(os.getenv("PG_CACHE_QUERY_TTL", str(CACHE_RETENTION_DAYS * 86400)))  # 30 days
PG_CACHE_STUDY_TTL: int = int(os.getenv("PG_CACHE_STUDY_TTL", str(CACHE_RETENTION_DAYS * 86400)))  # 30 days
PG_CACHE_MATCH_TTL: int = int(os.getenv("PG_CACHE_MATCH_TTL", str(CACHE_RETENTION_DAYS * 86400)))  # 30 days

# Groq LPU Real-Time Rephrasing Settings
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
GROQ_TIMEOUT_SECONDS: float = float(os.getenv("GROQ_TIMEOUT_SECONDS", "5.0"))

# OpenAI Fallback Settings
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_TIMEOUT_SECONDS: float = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "8.0"))



