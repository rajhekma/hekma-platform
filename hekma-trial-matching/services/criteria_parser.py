def parse_eligibility_criteria(criteria_text: str):
    """
    Splits raw eligibility text into structured inclusion and exclusion lists.
    """

    if not criteria_text:
        return [], []

    def refine(lines):
        return [l.strip() for l in lines if l.strip() and l.strip() != ":"]

    inclusion = []
    exclusion = []

    text_lower = criteria_text.lower()

    if "inclusion criteria" in text_lower:
        parts = criteria_text.split("Inclusion Criteria", 1)[1]
        if "Exclusion Criteria" in parts:
            inc_part, exc_part = parts.split("Exclusion Criteria", 1)
            inclusion = refine(inc_part.split("\n"))
            exclusion = refine(exc_part.split("\n"))
        else:
            inclusion = refine(parts.split("\n"))
    else:
        inclusion = refine(criteria_text.split("\n"))

    return inclusion, exclusion