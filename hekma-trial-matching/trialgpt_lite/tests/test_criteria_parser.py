"""
Unit tests for criteria text parser and demographic extraction.
"""

import unittest
from trialgpt_lite.parser.criteria_parser import (
    parse_age_to_years,
    extract_discrete_criteria,
    parse_eligibility_criteria,
    parse_demographics,
)


class TestCriteriaParser(unittest.TestCase):

    def test_parse_age_to_years(self):
        self.assertEqual(parse_age_to_years("18 Years"), 18.0)
        self.assertEqual(parse_age_to_years("65 Years"), 65.0)
        self.assertEqual(parse_age_to_years("6 Months"), 0.5)
        self.assertIsNone(parse_age_to_years("N/A"))
        self.assertIsNone(parse_age_to_years(None))
        self.assertIsNone(parse_age_to_years(""))

    def test_extract_discrete_criteria_bullets(self):
        text = """
* Age >= 18 years
* Histologically confirmed non-small cell lung cancer
* ECOG score 0 or 1
        """
        items = extract_discrete_criteria(text)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0], "Age >= 18 years")
        self.assertIn("lung cancer", items[1])

    def test_extract_discrete_criteria_numbers(self):
        text = """
1. Patient has signed informed consent.
2. Life expectancy > 12 weeks.
3. Adequate organ and marrow function.
        """
        items = extract_discrete_criteria(text)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0], "Patient has signed informed consent.")
        self.assertEqual(items[1], "Life expectancy > 12 weeks.")

    def test_parse_eligibility_criteria_standard(self):
        raw = """
Inclusion Criteria:
* Diagnosis of metastatic melanoma
* Age 18 to 75 years
* Measurable disease per RECIST 1.1

Exclusion Criteria:
* Active brain metastases
* Prior immunotherapy within 4 weeks
* Pregnant or breastfeeding women
        """
        parsed = parse_eligibility_criteria(raw)
        self.assertEqual(len(parsed.inclusion_criteria), 3)
        self.assertEqual(len(parsed.exclusion_criteria), 3)
        self.assertIn("metastatic melanoma", parsed.inclusion_criteria[0])
        self.assertIn("Active brain metastases", parsed.exclusion_criteria[0])

    def test_parse_eligibility_criteria_missing_exclusion(self):
        raw = """
Inclusion Criteria:
1. Adult patients with type 2 diabetes.
2. HbA1c between 7.5% and 10.5%.
        """
        parsed = parse_eligibility_criteria(raw)
        self.assertEqual(len(parsed.inclusion_criteria), 2)
        self.assertEqual(len(parsed.exclusion_criteria), 0)

    def test_parse_demographics(self):
        elig_module = {
            "minimumAge": "18 Years",
            "maximumAge": "70 Years",
            "sex": "FEMALE",
            "healthyVolunteers": False,
        }
        demo = parse_demographics(elig_module)
        self.assertEqual(demo.minimum_age_years, 18.0)
        self.assertEqual(demo.maximum_age_years, 70.0)
        self.assertEqual(demo.minimum_age_text, "18 Years")
        self.assertEqual(demo.maximum_age_text, "70 Years")
        self.assertEqual(demo.sex, "FEMALE")
        self.assertFalse(demo.healthy_volunteers)


if __name__ == "__main__":
    unittest.main()
