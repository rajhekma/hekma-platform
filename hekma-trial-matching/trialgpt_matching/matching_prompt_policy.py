"""
Shared instructions for criterion-level patient–trial matching (all LLM backends).

Aligned with clinical / AI team rules: anonymized dates must not drive age or
timeline inference; investigator-discretion criteria must not be substituted
by model judgment.
"""

MATCHING_POLICY_BLOCK = """

GLOBAL POLICY (mandatory — takes precedence over any generic instruction to infer or guess):

1) DATES AND AGE
   - Patient text may include anonymized or de-identified dates (e.g. date of birth, visit dates, procedure dates, lab dates). Treat those dates as UNRELIABLE for inferring chronological age or timelines.
   - Do NOT compute or infer age from: date of birth, birth date, birth year, phrases like "born on <date>", calendar years in isolation, or any dated event used only to derive how old the patient is.
   - For any criterion that requires verifying age (e.g. ">= 18 years", "18–65"): output label "not enough information" UNLESS the narrative explicitly states age as a clear numeric or direct statement (e.g. "Patient is 45 years old", "Age: 45", "45-year-old"). Vague terms alone ("adult", "elderly") are NOT sufficient for numeric age thresholds unless the criterion text explicitly accepts that wording and it clearly matches.

2) TIMELINES
   - Do not infer study eligibility windows (e.g. "within 3 months of X") from unreliable or anonymized dates in the profile. If timing cannot be verified from explicit, trustworthy statements, use "not enough information".

3) INVESTIGATOR JUDGMENT / OPINION
   - If the criterion depends on the investigator's, sponsor's, or study team's subjective judgment (e.g. "in the investigator's opinion", "at the investigator's discretion", "investigator considers", "would confound the study in the opinion of the investigator", "clinically significant as judged by the investigator"), do NOT substitute LLM reasoning for that human judgment.
   - For those criteria, output "not enough information" and briefly state that eligibility must be determined by the site study team.

"""
