"""OTEL PYTHONPATH shadow must not hide site-packages typing_extensions."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from docker_entrypoint import strip_otel_typing_shadow


class OtelTypingShadowTests(unittest.TestCase):
    def test_drops_otel_root_keeps_auto_instrumentation_and_site_packages(self):
        paths = [
            "/otel-auto-instrumentation-python/opentelemetry/instrumentation/auto_instrumentation",
            "/otel-auto-instrumentation-python",
            "/otel-auto-instrumentation-python/",
            "/usr/local/lib/python3.10/site-packages",
        ]
        out = strip_otel_typing_shadow(paths)
        self.assertEqual(
            out,
            [
                "/otel-auto-instrumentation-python/opentelemetry/instrumentation/auto_instrumentation",
                "/usr/local/lib/python3.10/site-packages",
            ],
        )


if __name__ == "__main__":
    unittest.main()
