"""Infer medication dosage form from dose text and optional drug name."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

from .medication_constants import MedicationType, normalize_medication_type

# (compiled pattern, canonical type) — first match wins; order matters.
_DOSE_FORM_PATTERNS: Tuple[Tuple[re.Pattern[str], MedicationType], ...] = (
    (re.compile(r"\b(suppositor(y|ies))\b", re.I), MedicationType.SUPPOSITORY),
    (
        re.compile(
            r"\b(odt|orally\s+disintegrating\s+tablet|chewable\s+tablet|"
            r"extended[\s-]?release\s+tablet|immediate[\s-]?release\s+tablet|"
            r"tab(?:let)?s?)\b",
            re.I,
        ),
        MedicationType.TABLET,
    ),
    (re.compile(r"\b(cap(?:sule)?s?)\b", re.I), MedicationType.CAPSULE),
    (
        re.compile(
            r"\b(oral\s+(liquid|solution|suspension)|suspension|syrup|"
            r"solution|elixir|susp\.)\b",
            re.I,
        ),
        MedicationType.LIQUID,
    ),
    (re.compile(r"\b\d+(?:\.\d+)?\s*ml\b", re.I), MedicationType.LIQUID),
    (
        re.compile(
            r"\b(iv|im|sc|subcutaneous|intramuscular|intravenous|injection|injectable)\b",
            re.I,
        ),
        MedicationType.INJECTION,
    ),
    (re.compile(r"\b(infusion|iv\s+infusion)\b", re.I), MedicationType.INFUSION_IV),
    (re.compile(r"\bsteam\s+inhalation\b", re.I), MedicationType.INHALER),
    (re.compile(r"\b(inhaler|puff|puffs|nebulizer)\b", re.I), MedicationType.INHALER),
    (re.compile(r"\b(nasal\s+spray)\b", re.I), MedicationType.NASAL_SPRAY),
    (re.compile(r"\b(ear\s+drops?)\b", re.I), MedicationType.EAR_DROPS),
    (re.compile(r"\b(eye\s+drops?|ophthalmic\s+drops?)\b", re.I), MedicationType.EYE_DROPS),
    (re.compile(r"\bdrops?\b", re.I), MedicationType.EYE_DROPS),
    (re.compile(r"\b(cream)\b", re.I), MedicationType.CREAM),
    (re.compile(r"\b(ointment)\b", re.I), MedicationType.OINTMENT),
    (re.compile(r"\b(gel)\b", re.I), MedicationType.GEL),
    (re.compile(r"\b(patch|transdermal)\b", re.I), MedicationType.PATCH),
    (re.compile(r"\b(powder)\b", re.I), MedicationType.POWDER),
)

# Common drugs and forms they may appear as (for hints / validation only).
# Prescription line prefixes (e.g. "Tab. Paracetamol", "Syp. Montair").
_NAME_PREFIX_FORMS: Tuple[Tuple[re.Pattern[str], MedicationType], ...] = (
    (re.compile(r"^\s*tab\.?\b", re.I), MedicationType.TABLET),
    (re.compile(r"^\s*cap\.?\b", re.I), MedicationType.CAPSULE),
    (re.compile(r"^\s*syp\.?\b", re.I), MedicationType.LIQUID),
    (re.compile(r"^\s*inj\.?\b", re.I), MedicationType.INJECTION),
    (re.compile(r"^\s*susp\.?\b", re.I), MedicationType.LIQUID),
    (re.compile(r"^\s*sol\.?\b", re.I), MedicationType.LIQUID),
)

COMMON_DRUG_ORAL_FORMS: dict[str, Tuple[str, ...]] = {
    "paracetamol": ("Tablet", "Capsule", "Liquid", "Suppository", "Injection"),
    "acetaminophen": ("Tablet", "Capsule", "Liquid", "Suppository", "Injection"),
    "amoxicillin": ("Capsule", "Tablet", "Liquid"),
    "ondansetron": ("Tablet", "Liquid", "Injection"),
    "ibuprofen": ("Tablet", "Capsule", "Liquid"),
    "morphine": ("Tablet", "Capsule", "Liquid", "Injection"),
    "metformin": ("Tablet",),
}


def _normalize_drug_key(name: str) -> str:
    text = (name or "").strip().lower()
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text.split()[0] if text else ""


def suggested_forms_for_drug(name: str) -> Tuple[str, ...]:
    """Return known possible forms for a drug name, or empty if unknown."""
    key = _normalize_drug_key(name)
    if not key:
        return ()
    for drug, forms in COMMON_DRUG_ORAL_FORMS.items():
        if key == drug or key.startswith(drug):
            return forms
    return ()


def _form_from_name_prefix(name: Optional[str]) -> Optional[str]:
    text = (name or "").strip()
    if not text:
        return None
    for pattern, med_type in _NAME_PREFIX_FORMS:
        if pattern.search(text):
            return med_type.value
    return None


def _match_form_in_text(*chunks: Iterable[str]) -> Optional[str]:
    blob = " ".join(str(c or "").strip() for c in chunks if c)
    if not blob.strip():
        return None
    for pattern, med_type in _DOSE_FORM_PATTERNS:
        if pattern.search(blob):
            return med_type.value
    return None


def infer_medication_type(
    name: Optional[str] = None,
    *,
    dosage: Optional[str] = None,
    how_much_to_take: Optional[str] = None,
    strength: Optional[str] = None,
    medication_type: Optional[str] = None,
) -> Optional[str]:
    """
    Choose a dosage form when the client did not send one.

    Explicit ``medicationType`` is kept when it is a known enum value. Otherwise
    infer from dose wording (e.g. ``1 tablet`` → Tablet, ``5 ml`` → Liquid).
    """
    explicit = normalize_medication_type(medication_type)
    if explicit and explicit in {t.value for t in MedicationType}:
        return explicit

    from_dose = _match_form_in_text(how_much_to_take, dosage, strength, name)
    if from_dose:
        return from_dose

    from_prefix = _form_from_name_prefix(name)
    if from_prefix:
        return from_prefix

    # Strength-only (e.g. "500 mg") does not imply tablet vs capsule.
    return explicit or None


def enrich_medicine_form_fields(medicine: Dict[str, Any]) -> Dict[str, Any]:
    """Fill ``medicationType`` and dose aliases on a scan/extraction medicine row."""
    result = dict(medicine)
    name = (result.get("name") or "").strip()
    dosage = (result.get("dosage") or "").strip()
    how_much = (result.get("howMuchToTake") or result.get("how_much_to_take") or "").strip()
    strength = (result.get("strength") or "").strip()
    instructions = (result.get("instructions") or "").strip()

    if not how_much and dosage:
        how_much = dosage
        result["howMuchToTake"] = how_much

    med_type = result.get("medicationType") or result.get("medication_type") or result.get("form")
    inferred = infer_medication_type(
        name,
        dosage=dosage or how_much,
        how_much_to_take=how_much,
        strength=strength,
        medication_type=med_type,
    )
    if not inferred and instructions:
        inferred = _match_form_in_text(instructions, name)
    if inferred:
        result["medicationType"] = inferred
    elif med_type is not None:
        normalized = normalize_medication_type(med_type)
        if normalized:
            result["medicationType"] = normalized

    return result


def enrich_extracted_medicines(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure each medicine in smart-scan ``extracted_data`` has form fields for preview."""
    if not extracted:
        return extracted
    result = dict(extracted)
    key = "medicines" if result.get("medicines") is not None else "medications"
    items = result.get(key) or result.get("medicines") or result.get("medications") or []
    if not items:
        return result
    enriched = [enrich_medicine_form_fields(dict(item)) for item in items]
    result["medicines"] = enriched
    if "medications" in result:
        result["medications"] = enriched
    return result
