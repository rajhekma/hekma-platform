"""
Uvicorn launcher that survives OpenTelemetry Python auto-instrumentation.

The OTEL operator prepends /otel-auto-instrumentation-python to PYTHONPATH.
That directory ships an old typing_extensions.py. Newer anyio/FastAPI import
typing_extensions.sentinel, the stub wins, and the pod crash-loops (nginx 503).

Keep the auto_instrumentation sitecustomize path; drop only the OTEL root that
shadows site-packages.
"""

from __future__ import annotations

import sys
from typing import Iterable, List

OTEL_TYPING_SHADOW_ROOT = "/otel-auto-instrumentation-python"


def strip_otel_typing_shadow(sys_path: Iterable[str]) -> List[str]:
    """Remove the OTEL agent root that contains a stale typing_extensions.py."""
    cleaned: List[str] = []
    for path in sys_path:
        if path.rstrip("/") == OTEL_TYPING_SHADOW_ROOT:
            continue
        cleaned.append(path)
    return cleaned


def unshadow_typing_extensions() -> None:
    sys.path[:] = strip_otel_typing_shadow(sys.path)
    sys.modules.pop("typing_extensions", None)


def main() -> None:
    unshadow_typing_extensions()
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, factory=False)


if __name__ == "__main__":
    main()
