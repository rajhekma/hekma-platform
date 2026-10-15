"""
TrialGPT Lite: Lightweight clinical trial condition matching engine powered by ClinicalTrials.gov REST API v2.
"""

from .service import TrialGPTLiteService
from .client.ctgov_client import ClinicalTrialsGovClient
from .matcher.llm_matcher import LLMCriteriaMatcher, RuleBasedCriteriaMatcher
from .schemas.request import MatchRequest, PatientProfile, ConditionSearchRequest
from .schemas.match_result import ConditionMatchReport, TrialMatchResult, OverallEligibility

__version__ = "1.0.0"

__all__ = [
    "TrialGPTLiteService",
    "ClinicalTrialsGovClient",
    "LLMCriteriaMatcher",
    "RuleBasedCriteriaMatcher",
    "MatchRequest",
    "PatientProfile",
    "ConditionSearchRequest",
    "ConditionMatchReport",
    "TrialMatchResult",
    "OverallEligibility",
]

