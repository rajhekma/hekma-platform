"""Unit tests for trialgpt_corpus bootstrap delegation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories import trialgpt_corpus_repo


class EnsureTrialgptCorpusTableTests(unittest.TestCase):
    @patch("repositories.trialgpt_corpus_repo.ensure_trialgpt_schema")
    def test_ensure_delegates_to_full_schema(self, mock_ensure):
        trialgpt_corpus_repo.ensure_trialgpt_corpus_table()
        trialgpt_corpus_repo.ensure_trialgpt_corpus_table()
        self.assertEqual(mock_ensure.call_count, 2)


if __name__ == "__main__":
    unittest.main()
