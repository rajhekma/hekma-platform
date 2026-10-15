"""
Criteria text parser and demographic normalizer.
Handles multiple ClinicalTrials.gov criteria formatting conventions.
"""

import re
from typing import Optional
from trialgpt_lite.schemas.study import DemographicCriteria, ParsedCriteria


def parse_age_to_years(age_str: Optional[str]) -> Optional[float]:
    """
    Parses ClinicalTrials.gov age string (e.g. '18 Years', '6 Months', '28 Days')
    into numeric years. Returns None if unconstrained / N/A.
    """
    if not age_str or age_str.strip().upper() in ["N/A", "NONE", ""]:
        return None

    clean_str = age_str.strip().lower()
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(year|month|week|day|hour)s?", clean_str)
    if not match:
        return None

    value = float(match.group(1))
    unit = match.group(2)

    if unit == "year":
        return value
    elif unit == "month":
        return round(value / 12.0, 2)
    elif unit == "week":
        return round(value / 52.0, 3)
    elif unit == "day":
        return round(value / 365.25, 3)
    elif unit == "hour":
        return round(value / (365.25 * 24.0), 4)

    return value


def extract_discrete_criteria(text: str) -> list[str]:
    """
    Splits a criteria text block into distinct individual criteria items.
    Handles bullets (*, -, •), numbered lists (1., 2.), and paragraph splits.
    """
    if not text:
        return []

    lines = text.strip().split("\n")
    items: list[str] = []
    current_item: list[str] = []

    # Regex detecting start of a new criterion item
    # e.g., "* ", "- ", "• ", "1. ", "1) ", "(1) ", "[1] "
    bullet_pattern = re.compile(
        r"^(?:[\*\-\•\–\—]\s+|\(?\d+[\.\)\]]\s+|\(?[a-zA-Z][\.\)]\s+)"
    )

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current_item:
                full_item = " ".join(current_item).strip()
                if len(full_item) > 3:
                    items.append(full_item)
                current_item = []
            continue

        # If line starts with bullet or numbering, finalize previous and start new
        if bullet_pattern.match(stripped):
            if current_item:
                full_item = " ".join(current_item).strip()
                if len(full_item) > 3:
                    items.append(full_item)
                current_item = []
            # Strip the bullet prefix itself to get clean text
            cleaned_line = bullet_pattern.sub("", stripped).strip()
            current_item.append(cleaned_line)
        else:
            # Continuation of previous item or new paragraph
            if not current_item:
                current_item.append(stripped)
            else:
                current_item.append(stripped)

    if current_item:
        full_item = " ".join(current_item).strip()
        if len(full_item) > 3:
            items.append(full_item)

    # Edge case: If no bullets/paragraphs were parsed, split by double newlines or semicolons
    if len(items) <= 1 and ";" in text:
        semi_items = [s.strip() for s in text.split(";") if len(s.strip()) > 3]
        if len(semi_items) > 1:
            return semi_items

    return items


def parse_eligibility_criteria(raw_criteria: Optional[str]) -> ParsedCriteria:
    """
    Splits raw eligibility criteria text into inclusion and exclusion lists.
    Handles varied header patterns (e.g. 'Inclusion Criteria:', 'KEY INCLUSION',
    markdown escaped '\\*Inclusion Criteria:', and multi-cohort protocols).
    """
    if not raw_criteria or not raw_criteria.strip():
        return ParsedCriteria(inclusion_criteria=[], exclusion_criteria=[], raw_text="")

    text = raw_criteria.strip()

    # Pattern matching any Inclusion or Exclusion header line across cohorts
    # Handles leading bullets, markdown escape slashes, hashtags, and whitespace
    header_pattern = re.compile(
        r"(?:^|\n)[ \t*#_>\\\-]*(?:key\s+)?(inclusion|exclusion)(?:\s+criteria)?\s*:?",
        re.IGNORECASE,
    )

    matches = list(header_pattern.finditer(text))

    if not matches:
        # Fallback: Header not found, treat whole text as inclusion criteria
        inclusion_list = extract_discrete_criteria(text)
        return ParsedCriteria(
            inclusion_criteria=inclusion_list,
            exclusion_criteria=[],
            raw_text=raw_criteria,
        )

    inc_chunks: list[str] = []
    exc_chunks: list[str] = []

    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        kind = match.group(1).lower()

        if kind == "inclusion":
            inc_chunks.append(chunk)
        else:
            exc_chunks.append(chunk)

    clean_inc: list[str] = []
    for c in inc_chunks:
        clean_inc.extend(extract_discrete_criteria(c))

    clean_exc: list[str] = []
    for c in exc_chunks:
        clean_exc.extend(extract_discrete_criteria(c))

    # Filter out residual header-like fragments
    header_garbage = re.compile(r"^(?:inclusion|exclusion)\s*criteria:?$", re.IGNORECASE)
    clean_inc = [item for item in clean_inc if not header_garbage.match(item) and len(item) > 3]
    clean_exc = [item for item in clean_exc if not header_garbage.match(item) and len(item) > 3]

    # De-duplicate while preserving insertion order
    seen_inc = set()
    dedup_inc = []
    for x in clean_inc:
        norm = x.lower().strip()
        if norm not in seen_inc:
            seen_inc.add(norm)
            dedup_inc.append(x)

    seen_exc = set()
    dedup_exc = []
    for x in clean_exc:
        norm = x.lower().strip()
        if norm not in seen_exc:
            seen_exc.add(norm)
            dedup_exc.append(x)

    return ParsedCriteria(
        inclusion_criteria=dedup_inc,
        exclusion_criteria=dedup_exc,
        raw_text=raw_criteria,
    )


def parse_demographics(eligibility_module: dict) -> DemographicCriteria:
    """Extracts and standardizes demographic restrictions from eligibility module."""
    min_age_str = eligibility_module.get("minimumAge")
    max_age_str = eligibility_module.get("maximumAge")
    sex_str = eligibility_module.get("sex", "ALL").upper()
    healthy = eligibility_module.get("healthyVolunteers")

    return DemographicCriteria(
        minimum_age_years=parse_age_to_years(min_age_str),
        maximum_age_years=parse_age_to_years(max_age_str),
        minimum_age_text=min_age_str,
        maximum_age_text=max_age_str,
        sex=sex_str if sex_str in ["ALL", "FEMALE", "MALE"] else "ALL",
        healthy_volunteers=healthy,
    )
