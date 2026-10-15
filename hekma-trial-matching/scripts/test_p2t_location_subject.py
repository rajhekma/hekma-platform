"""Unit tests for US location expansion and subject_id placeholder handling."""

from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repositories.mysql_repo import resolve_subject_id
from repositories.trialgpt_corpus_repo import _expand_location_match_terms


class LocationExpandTests(unittest.TestCase):
    def test_us_expands_to_united_states_phrases(self):
        terms = _expand_location_match_terms(["US"])
        self.assertIn("united states", terms)
        self.assertIn("usa", terms)
        self.assertIn("us", terms)

    def test_city_passthrough(self):
        terms = _expand_location_match_terms(["Miami, Florida, United States"])
        self.assertIn("miami, florida, united states", terms)


class SubjectIdResolveTests(unittest.TestCase):
    def test_rejects_undefined_placeholder(self):
        sid = resolve_subject_id("undefined", 203563)
        expected = str(
            uuid.uuid5(uuid.NAMESPACE_URL, "hekma:patient:203563")
        )
        self.assertEqual(sid, expected)

    def test_keeps_real_uuid(self):
        real = "00c13f8d-c0c1-55f2-b2d5-eab8ea4fdae2"
        self.assertEqual(resolve_subject_id(real, 203450), real)

    def test_null_string_falls_back(self):
        sid = resolve_subject_id("null", 1)
        self.assertTrue(sid)
        self.assertNotEqual(sid.lower(), "null")


if __name__ == "__main__":
    unittest.main()
