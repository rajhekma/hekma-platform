"""Score Vision extract against printed ground truth — extra rows count as hallucination."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .strategies import build_strategy_registry

ARRAY_KEY = {
    "allergies": "allergies",
    "lab_reports": "lab_results",
    "vital_signs": "vitals",
    "immunization": "immunizations",
    "procedures": "procedures",
    "diagnosis": "conditions",
}

NAME_FIELD = {
    "allergies": "substance",
    "lab_reports": "testName",
    "vital_signs": "type",
    "immunization": "vaccineName",
    "procedures": "procedureName",
    "diagnosis": "conditionName",
}

VALUE_FIELDS = {
    "allergies": ("reaction",),
    "lab_reports": ("testValue", "value"),
    "vital_signs": ("refValue1", "value"),
    "immunization": ("vaccinationDate",),
    "procedures": ("outcome", "notes"),
    "diagnosis": ("notes",),
}

VALUE2_FIELDS = {
    "vital_signs": ("refValue2", "value2"),
}

VITAL_CANON = {
    "bp": "blood pressure",
    "blood pressure": "blood pressure",
    "pulse": "heart rate",
    "heart rate": "heart rate",
    "pulse heart rate": "heart rate",
    "hr": "heart rate",
    "temperature": "temperature",
    "temp": "temperature",
    "respiratory rate": "respiratory rate",
    "rr": "respiratory rate",
    "resp rate": "respiratory rate",
    "spo2": "spo2",
    "sp o2": "spo2",
    "oxygen saturation": "spo2",
    "height": "height",
    "weight": "weight",
    "bmi": "bmi",
    "body mass index": "bmi",
}

LAB_CANON = {
    "hb": "hemoglobin",
    "hgb": "hemoglobin",
    "hemoglobin": "hemoglobin",
    "haemoglobin": "hemoglobin",
    "wbc": "wbc",
    "tlc": "wbc",
    "white blood cell": "wbc",
    "white blood cells": "wbc",
    "sgpt": "alt",
    "sgpt alt": "alt",
    "alt": "alt",
    "hba1c": "hba1c",
    "hb a1c": "hba1c",
}

IMMUN_CANON = {
    "tt": "tetanus",
    "tetanus": "tetanus",
    "tetanus tt": "tetanus",
    "hep b": "hepatitis b",
    "hepatitis b": "hepatitis b",
    "covid 19": "covid 19",
    "covid": "covid 19",
}

PROC_CANON = {
    "ecg": "ecg",
    "ekg": "ecg",
    "electrocardiogram": "ecg",
    "chest x ray": "chest x ray",
    "cxr": "chest x ray",
    "chest xray": "chest x ray",
}


def normalize_label(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    cleaned = re.sub(r"[^a-z0-9]+", " ", (text or "").lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _canon(text: str, table: Dict[str, str]) -> str:
    key = normalize_label(text)
    return table.get(key, key)


def canonical_name(module: str, text: str) -> str:
    """Map a printed/extracted label onto a comparison key for that module."""
    if module == "vital_signs":
        return _canon(text, VITAL_CANON)
    if module == "lab_reports":
        return _canon(text, LAB_CANON)
    if module == "immunization":
        return _canon(text, IMMUN_CANON)
    if module == "procedures":
        return _canon(text, PROC_CANON)
    return normalize_label(text)


def names_match(module: str, expected: str, got: str, aliases: Sequence[str] = ()) -> bool:
    """True when extracted label is the same printed concept as expected."""
    left = canonical_name(module, expected)
    right = canonical_name(module, got)
    if left and right and left == right:
        return True
    extra = {canonical_name(module, a) for a in aliases if a}
    if right in extra:
        return True
    if left and right and len(left) >= 4 and len(right) >= 4:
        if left in right or right in left:
            return True
    return False


def numeric_tokens(text: Any) -> List[str]:
    """Pull decimal numbers from a printed or extracted value."""
    return re.findall(r"\d+(?:\.\d+)?", str(text or ""))


def values_compatible(expected: str, got: str) -> bool:
    """True when every expected number appears in the extracted value text."""
    want = numeric_tokens(expected)
    if not want:
        return True
    have = numeric_tokens(got)
    if not have:
        return False
    return all(n in have for n in want)


@dataclass(frozen=True)
class ExpectedItem:
    name: str
    value: str = ""
    value2: str = ""
    aliases: Tuple[str, ...] = ()


@dataclass
class ModuleScore:
    module: str
    expected_names: List[str]
    extracted_names: List[str]
    hits: List[str] = field(default_factory=list)
    misses: List[str] = field(default_factory=list)
    hallucinations: List[str] = field(default_factory=list)
    value_mismatches: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.misses and not self.hallucinations and not self.value_mismatches


@dataclass
class ExtractionScore:
    fixture_id: str
    expected_modules: List[str]
    detected_modules: List[str]
    extra_modules: List[str]
    missing_modules: List[str]
    modules: Dict[str, ModuleScore]
    leaks: List[str] = field(default_factory=list)

    @property
    def hallucination_count(self) -> int:
        extra_mod = len(self.extra_modules)
        extra_rows = sum(len(m.hallucinations) for m in self.modules.values())
        return extra_mod + extra_rows + len(self.leaks)

    @property
    def miss_count(self) -> int:
        missing_mod = len(self.missing_modules)
        missing_rows = sum(len(m.misses) for m in self.modules.values())
        return missing_mod + missing_rows

    @property
    def value_mismatch_count(self) -> int:
        return sum(len(m.value_mismatches) for m in self.modules.values())

    @property
    def passed(self) -> bool:
        return (
            not self.extra_modules
            and not self.missing_modules
            and not self.leaks
            and all(m.ok for m in self.modules.values())
        )


def map_extracted_records(extracted: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Run production map_records so scoring matches what would persist."""
    mapped: Dict[str, List[Dict[str, Any]]] = {}
    for module, strategy in build_strategy_registry().items():
        mapped[module.value] = strategy.map_records(extracted)
    return mapped


def _item_name(module: str, row: Dict[str, Any]) -> str:
    return str(row.get(NAME_FIELD[module]) or "").strip()


def _item_value(module: str, row: Dict[str, Any]) -> str:
    parts = [str(row.get(f) or "") for f in VALUE_FIELDS.get(module, ())]
    if module in VALUE2_FIELDS:
        parts.extend(str(row.get(f) or "") for f in VALUE2_FIELDS[module])
    return " ".join(p for p in parts if p).strip()


def _match_expected(
    module: str,
    expected: ExpectedItem,
    rows: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for row in rows:
        if names_match(module, expected.name, _item_name(module, row), expected.aliases):
            return row
    return None


def score_extraction(
    fixture_id: str,
    expected_modules: Iterable[str],
    expected_items: Dict[str, Sequence[ExpectedItem]],
    extracted: Dict[str, Any],
    *,
    expect_no_clinical_data: bool = False,
) -> ExtractionScore:
    """
    Compare mapped extract to printed ground truth.

    Extra modules/rows are hallucinations. Missing printed rows are misses.
    Value checks apply when ground truth includes a number.
    """
    mapped = map_extracted_records(extracted)
    expected_set = [m for m in ARRAY_KEY if m in set(expected_modules)]
    detected = [m for m in ARRAY_KEY if mapped.get(m)]
    if expect_no_clinical_data:
        extra = detected[:]
        return ExtractionScore(
            fixture_id=fixture_id,
            expected_modules=[],
            detected_modules=detected,
            extra_modules=extra,
            missing_modules=[],
            modules={},
        )

    extra_modules = [m for m in detected if m not in expected_set]
    missing_modules = [m for m in expected_set if m not in detected]

    module_scores: Dict[str, ModuleScore] = {}
    claimed: Dict[str, List[Dict[str, Any]]] = {m: list(mapped.get(m) or []) for m in ARRAY_KEY}

    for module in ARRAY_KEY:
        want = list(expected_items.get(module) or [])
        rows = claimed[module]
        extracted_names = [_item_name(module, r) for r in rows if _item_name(module, r)]
        score = ModuleScore(
            module=module,
            expected_names=[i.name for i in want],
            extracted_names=extracted_names,
        )
        used = set()
        for item in want:
            match = None
            for idx, row in enumerate(rows):
                if idx in used:
                    continue
                if names_match(module, item.name, _item_name(module, row), item.aliases):
                    match = row
                    used.add(idx)
                    break
            if match is None:
                score.misses.append(item.name)
                continue
            score.hits.append(item.name)
            got_value = _item_value(module, match)
            if item.value and not values_compatible(item.value, got_value + " " + _item_name(module, match)):
                score.value_mismatches.append(
                    f"{item.name}: expected {item.value} got {got_value or '(empty)'}"
                )
            if item.value2 and not values_compatible(item.value2, got_value):
                score.value_mismatches.append(
                    f"{item.name}: expected diastolic/value2 {item.value2} got {got_value or '(empty)'}"
                )
        for idx, row in enumerate(rows):
            if idx not in used:
                label = _item_name(module, row) or f"(unnamed {module} row)"
                score.hallucinations.append(label)
        if want or rows:
            module_scores[module] = score

    leaks: List[str] = []
    for module, items in expected_items.items():
        if module not in ARRAY_KEY:
            continue
        for item in items:
            for other, rows in claimed.items():
                if other == module:
                    continue
                hit = _match_expected(other, ExpectedItem(item.name, aliases=item.aliases), rows)
                if hit:
                    leaks.append(
                        f"{item.name} belongs in {module} but also appeared in {other}"
                    )

    return ExtractionScore(
        fixture_id=fixture_id,
        expected_modules=expected_set,
        detected_modules=detected,
        extra_modules=extra_modules,
        missing_modules=missing_modules,
        modules=module_scores,
        leaks=leaks,
    )
