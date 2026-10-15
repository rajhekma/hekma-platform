"""Unit tests for matching pipeline schema wrapper."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories import matching_pipeline_schema


class EnsureMatchingPipelineTablesTests(unittest.TestCase):
    @patch("repositories.matching_pipeline_schema.ensure_trialgpt_schema")
    def test_ensure_delegates_to_full_schema(self, mock_ensure):
        matching_pipeline_schema.ensure_matching_pipeline_tables()
        mock_ensure.assert_called_once()


if __name__ == "__main__":
    unittest.main()
