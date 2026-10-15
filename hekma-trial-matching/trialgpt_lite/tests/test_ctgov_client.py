"""
Unit tests for ClinicalTrialsGovClient.
"""

import unittest
from trialgpt_lite.client.ctgov_client import ClinicalTrialsGovClient


class TestClinicalTrialsGovClient(unittest.TestCase):

    def setUp(self):
        self.client = ClinicalTrialsGovClient()

    def test_relax_query_removes_qualifiers(self):
        query = "Stage IV Metastatic Melanoma EGFR+ Recurrent"
        relaxed = self.client._relax_query(query)
        self.assertIsNotNone(relaxed)
        self.assertNotIn("stage iv", relaxed.lower())
        self.assertNotIn("metastatic", relaxed.lower())
        self.assertIn("melanoma", relaxed.lower())

    def test_relax_query_returns_none_if_too_short(self):
        query = "Stage IV"
        relaxed = self.client._relax_query(query)
        self.assertIsNone(relaxed)

    def test_live_search_condition_basic(self):
        # Quick live query test to verify network connectivity and JSON structure
        result = self.client.search_by_condition(
            condition="type 2 diabetes",
            page_size=2,
            count_total=True,
        )
        self.assertGreater(result["total_count"], 0)
        self.assertGreater(len(result["studies"]), 0)
        first_study = result["studies"][0]
        self.assertIn("protocolSection", first_study)


if __name__ == "__main__":
    unittest.main()
