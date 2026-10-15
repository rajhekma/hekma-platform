"""CORS settings for TrialGPT API — avoid per-subdomain edits in main.py."""

from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

# Local Vite / Next dev servers (not covered by hekma.ai regex).
_LOCAL_ORIGINS: Tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "https://localhost:3000",
    "http://127.0.0.1:3000",
    "https://127.0.0.1:3000",
)

# Any depth of subdomain on hekma.ai (patient.test, sponsor.demo, dev, apex, optional port).
_DEFAULT_HEKMA_ORIGIN_REGEX = (
    r"^https?://([a-zA-Z0-9-]+\.)*hekma\.ai(?::\d+)?$"
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def resolve_cors_allowlist() -> Tuple[List[str], Optional[str]]:
    """
    Returns (allow_origins, allow_origin_regex) for Starlette CORSMiddleware.

    - Localhost origins are always allowed.
    - CORS_EXTRA_ORIGINS: comma-separated extra exact origins (partners, previews).
    - CORS_ALLOW_HEKMA_SUBDOMAINS (default true): allow any https?://*.hekma.ai
    - CORS_ORIGIN_REGEX: override the default hekma.ai pattern entirely
    """
    origins: List[str] = list(_LOCAL_ORIGINS)
    extra = os.getenv("CORS_EXTRA_ORIGINS", "").strip()
    if extra:
        origins.extend(part.strip() for part in extra.split(",") if part.strip())

    custom_regex = os.getenv("CORS_ORIGIN_REGEX", "").strip()
    if custom_regex:
        return origins, custom_regex

    if _env_bool("CORS_ALLOW_HEKMA_SUBDOMAINS", True):
        return origins, _DEFAULT_HEKMA_ORIGIN_REGEX

    return origins, None


def origin_allowed(origin: str, allow_origins: List[str], allow_regex: Optional[str]) -> bool:
    """Mirror Starlette CORS check (for unit tests)."""
    if not origin:
        return False
    if origin in allow_origins:
        return True
    if allow_regex and re.fullmatch(allow_regex, origin):
        return True
    return False
