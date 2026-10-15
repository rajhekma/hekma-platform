"""OpenAPI and Swagger UI Example Fixtures for PII/PHI Security Microservice.

Provides rich, realistic, interactive request body and response examples with
standard happy paths and critical clinical edge cases for FastAPI Swagger UI (/docs).
"""

# ==============================================================================
# 1. FHIR & Structured Ingress Examples (/api/v1/anonymize/fhir, /batch, /json)
# ==============================================================================

FHIR_ANONYMIZE_REQUEST_EXAMPLES = {
    "patient_demographics": {
        "summary": "1. Patient Demographics (Standard EHR Ingress)",
        "description": "FHIR Patient resource containing official names, birth date, telecom, and multi-line residential address.",
        "value": {
            "org_id": "203674",
            "resource": {
                "resourceType": "Patient",
                "id": "pat-203674",
                "name": [
                    {
                        "use": "official",
                        "family": "Fisher",
                        "given": ["Elijah"]
                    }
                ],
                "birthDate": "1979-05-18",
                "gender": "male",
                "telecom": [
                    {"system": "phone", "value": "555-234-5678"},
                    {"system": "email", "value": "privacyds@mailinator.com"}
                ],
                "address": [
                    {
                        "line": ["123 Main Street", "Apt 4B"],
                        "city": "Boston",
                        "state": "MA",
                        "postalCode": "02115"
                    }
                ]
            }
        }
    },
    "clinical_condition": {
        "summary": "2. Clinical Condition (Preserving ICD-10 & SNOMED)",
        "description": "FHIR Condition resource demonstrating that clinical diagnosis codes (ICD-10, SNOMED) are preserved 100% in cleartext while personal names inside notes are masked.",
        "value": {
            "org_id": "203674",
            "resource": {
                "resourceType": "Condition",
                "id": "cond-101",
                "code": {
                    "coding": [
                        {
                            "system": "http://hl7.org/fhir/sid/icd-10-cm",
                            "code": "E11.9",
                            "display": "Type 2 diabetes mellitus without complications"
                        },
                        {
                            "system": "http://snomed.info/sct",
                            "code": "44054006",
                            "display": "Diabetes mellitus type 2"
                        }
                    ]
                },
                "note": [
                    {
                        "text": "Patient Elijah Fisher advised by Dr. Sarah Connor to monitor glycemic index daily."
                    }
                ]
            }
        }
    },
    "lab_observation": {
        "summary": "3. Lab Observation (Preserving LOINC & Quantities)",
        "description": "FHIR Observation resource showing preserved LOINC code (29463-7) and numeric valueQuantity (76.5 kg), with provider name pseudonymized.",
        "value": {
            "org_id": "203674",
            "resource": {
                "resourceType": "Observation",
                "id": "obs-201",
                "code": {
                    "coding": [
                        {
                            "system": "http://loinc.org",
                            "code": "29463-7",
                            "display": "Body weight"
                        }
                    ]
                },
                "valueQuantity": {
                    "value": 76.5,
                    "unit": "kg",
                    "system": "http://unitsofmeasure.org",
                    "code": "kg"
                },
                "performer": [
                    {"display": "Dr. Sarah Connor"}
                ]
            }
        }
    },
    "edge_case_fhir_bundle": {
        "summary": "4. Edge Case: Complete FHIR Bundle (Mixed Entries)",
        "description": "FHIR transaction Bundle with multiple disparate resources in an entry array, verifying recursive batch anonymization across resource types.",
        "value": {
            "org_id": "203674",
            "resource": {
                "resourceType": "Bundle",
                "type": "collection",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "Patient",
                            "id": "pat-203674",
                            "name": [{"family": "Fisher", "given": ["Elijah"]}],
                            "birthDate": "1979-05-18"
                        }
                    },
                    {
                        "resource": {
                            "resourceType": "Condition",
                            "id": "cond-101",
                            "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "E11.9"}]}
                        }
                    }
                ]
            }
        }
    },
    "edge_case_pre_anonymized": {
        "summary": "5. Edge Case: Idempotent / Pre-Anonymized Resource",
        "description": "Resource that already has surrogate tokens (FAM_*, GIVEN_*). Verifies idempotency without double-masking or corrupted tokens.",
        "value": {
            "org_id": "203674",
            "resource": {
                "resourceType": "Patient",
                "id": "PAT_aa6277b940",
                "name": [
                    {
                        "use": "official",
                        "family": "FAM_3a99f959",
                        "given": ["GIVEN_c99d783c"]
                    }
                ],
                "birthDate": "1979-01-01",
                "gender": "male"
            }
        }
    },
    "edge_case_accents_and_intl": {
        "summary": "6. Edge Case: International Names & Special Characters",
        "description": "Patient with accented letters (José Peña-García), international phone (+1-800-555-0199), and hyphenated postal code (02115-3211).",
        "value": {
            "org_id": "203674",
            "resource": {
                "resourceType": "Patient",
                "id": "pat-intl-99",
                "name": [
                    {
                        "use": "official",
                        "family": "Peña-García",
                        "given": ["José", "María"]
                    }
                ],
                "telecom": [
                    {"system": "phone", "value": "+1-800-555-0199"}
                ],
                "address": [
                    {
                        "line": ["Avenida de la Constitución 45"],
                        "city": "San Juan",
                        "postalCode": "00901-1234"
                    }
                ]
            }
        }
    }
}

FHIR_ANONYMIZE_RESPONSE_EXAMPLES = {
    "patient_demographics_response": {
        "summary": "1. Patient Demographics Anonymized (200 OK)",
        "value": {
            "anonymized_resource": {
                "resourceType": "Patient",
                "id": "PAT_aa6277b940",
                "name": [
                    {
                        "use": "official",
                        "family": "FAM_3a99f959",
                        "given": ["GIVEN_c99d783c"]
                    }
                ],
                "birthDate": "1979-01-01",
                "gender": "male",
                "telecom": [
                    {"system": "phone", "value": "PHONE_a61f1019"},
                    {"system": "email", "value": "EMAIL_d58213f3"}
                ],
                "address": [
                    {
                        "line": ["[REDACTED STREET ADDRESS]"],
                        "city": "Boston",
                        "state": "MA",
                        "postalCode": "021XX"
                    }
                ]
            },
            "mappings_count": 4,
            "mappings": [
                {"entity_type": "FAMILY_NAME", "original_value": "Fisher", "tokenized_value": "FAM_3a99f959"},
                {"entity_type": "GIVEN_NAME", "original_value": "Elijah", "tokenized_value": "GIVEN_c99d783c"},
                {"entity_type": "PHONE", "original_value": "555-234-5678", "tokenized_value": "PHONE_a61f1019"},
                {"entity_type": "EMAIL", "original_value": "privacyds@mailinator.com", "tokenized_value": "EMAIL_d58213f3"}
            ]
        }
    },
    "condition_response": {
        "summary": "2. Clinical Condition Anonymized (Ontology Preserved)",
        "value": {
            "anonymized_resource": {
                "resourceType": "Condition",
                "id": "cond-101",
                "code": {
                    "coding": [
                        {
                            "system": "http://hl7.org/fhir/sid/icd-10-cm",
                            "code": "E11.9",
                            "display": "Type 2 diabetes mellitus without complications"
                        },
                        {
                            "system": "http://snomed.info/sct",
                            "code": "44054006",
                            "display": "Diabetes mellitus type 2"
                        }
                    ]
                },
                "note": [
                    {
                        "text": "Patient GIVEN_c99d783c FAM_3a99f959 advised by [PERSON_35a29afa] to monitor glycemic index daily."
                    }
                ]
            },
            "mappings_count": 3,
            "mappings": [
                {"entity_type": "NAME", "original_value": "Elijah Fisher", "tokenized_value": "GIVEN_c99d783c FAM_3a99f959"},
                {"entity_type": "DOCTOR_NAME", "original_value": "Dr. Sarah Connor", "tokenized_value": "[PERSON_35a29afa]"}
            ]
        }
    }
}

FHIR_BATCH_REQUEST_EXAMPLES = {
    "standard_clinical_bundle": {
        "summary": "1. Multi-Resource Batch (Condition + Observation)",
        "description": "Standard batch containing diagnosis (Condition) and vitals (Observation) for high-throughput pipeline ingestion.",
        "value": {
            "org_id": "203674",
            "resources": [
                {
                    "resourceType": "Condition",
                    "id": "cond-101",
                    "code": {
                        "coding": [
                            {"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "E11.9", "display": "Type 2 diabetes"}
                        ]
                    },
                    "note": [{"text": "Patient Elijah Fisher advised by Dr. Sarah Connor to monitor diet."}]
                },
                {
                    "resourceType": "Observation",
                    "id": "obs-201",
                    "code": {
                        "coding": [{"system": "http://loinc.org", "code": "29463-7", "display": "Body weight"}]
                    },
                    "valueQuantity": {"value": 76.5, "unit": "kg"},
                    "performer": [{"display": "Dr. Sarah Connor"}]
                }
            ]
        }
    },
    "edge_case_empty_notes": {
        "summary": "2. Edge Case: Empty / Null Notes & Minimal Resources",
        "description": "Batch resources where clinical notes are empty array or empty string, confirming null-safety.",
        "value": {
            "org_id": "203674",
            "resources": [
                {
                    "resourceType": "Condition",
                    "id": "cond-102",
                    "code": {
                        "coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "I10", "display": "Essential hypertension"}]
                    },
                    "note": []
                }
            ]
        }
    }
}

FHIR_BATCH_RESPONSE_EXAMPLES = {
    "standard_batch_response": {
        "summary": "Batch Anonymization Complete (200 OK)",
        "value": {
            "anonymized_resources": [
                {
                    "resourceType": "Condition",
                    "id": "cond-101",
                    "code": {
                        "coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "E11.9", "display": "Type 2 diabetes"}]
                    },
                    "note": [{"text": "Patient GIVEN_c99d783c FAM_3a99f959 advised by [PERSON_35a29afa] to monitor diet."}]
                },
                {
                    "resourceType": "Observation",
                    "id": "obs-201",
                    "code": {
                        "coding": [{"system": "http://loinc.org", "code": "29463-7", "display": "Body weight"}]
                    },
                    "valueQuantity": {"value": 76.5, "unit": "kg"},
                    "performer": [{"display": "[PERSON_35a29afa]"}]
                }
            ],
            "total_mappings_count": 3
        }
    }
}

GENERIC_JSON_REQUEST_EXAMPLES = {
    "standard_ehr_json": {
        "summary": "1. Standard Nested Clinical JSON",
        "description": "Generic JSON structure from Fasten Health or hospital data export.",
        "value": {
            "org_id": "203674",
            "resource": {
                "patient_info": {
                    "full_name": "Elijah Fisher",
                    "dob": "1979-05-18",
                    "contact_phone": "555-234-5678"
                },
                "encounter": {
                    "provider": "Dr. Sarah Connor",
                    "reason": "Routine diabetic checkup"
                }
            }
        }
    },
    "edge_case_deep_nesting": {
        "summary": "2. Edge Case: Deeply Nested Hierarchy (4+ levels)",
        "description": "Deeply nested dictionaries and lists testing recursive anonymization.",
        "value": {
            "org_id": "203674",
            "resource": {
                "level1": {
                    "level2": {
                        "level3": {
                            "level4": {
                                "subject": "Patient Elijah Fisher",
                                "clinician": "Dr. Sarah Connor"
                            }
                        }
                    }
                }
            }
        }
    }
}

RESTORE_JSON_REQUEST_EXAMPLES = {
    "standard_restore_json": {
        "summary": "1. Restore Nested JSON for UI Display",
        "description": "Reverses surrogate tokens embedded inside nested clinical JSON objects.",
        "value": {
            "org_id": "203674",
            "purpose": "patient_care",
            "data": {
                "patient": {
                    "id": "203674",
                    "name": "GIVEN_c99d783c FAM_3a99f959",
                    "phone": "PHONE_a61f1019"
                },
                "clinical_summary": "Type 2 diabetes managed by [PERSON_35a29afa]"
            }
        }
    }
}

# ==============================================================================
# 2. Unified Clean Top-Level Endpoints (/anonymize & /restore)
# ==============================================================================

UNIFIED_ANONYMIZE_REQUEST_EXAMPLES = {
    "mode_a_free_text": {
        "summary": "1. Mode A: Free-Text Clinical Note (Doctor Narrative)",
        "description": "Clinical narrative with patient name, attending doctor, phone number, and diagnosis.",
        "value": {
            "text": "Patient Elijah Fisher had severe anaphylaxis. Diagnosed by Dr. Robert Smith. Call 555-0199.",
            "org_id": "203674"
        }
    },
    "mode_b_structured_json": {
        "summary": "2. Mode B: Structured JSON Payload",
        "description": "Pass arbitrary JSON data to anonymize all identifying string attributes.",
        "value": {
            "json_data": {
                "patient_name": "Elijah Fisher",
                "phone": "555-234-5678",
                "diagnosis": "Type 2 diabetes mellitus"
            },
            "org_id": "203674"
        }
    },
    "edge_case_medical_eponyms": {
        "summary": "3. Edge Case: Medical Eponyms & Named Diseases",
        "description": "Validates that clinical diseases named after physicians (Parkinson's, Alzheimer's, Schilling test) are NOT falsely masked as patient names.",
        "value": {
            "text": "Patient evaluated for Parkinson's disease, Alzheimer dementia, and Fallopian tube inflammation. Ordered Schilling test.",
            "org_id": "203674"
        }
    },
    "edge_case_zero_pii": {
        "summary": "4. Edge Case: Clean Clinical Text (Zero PII)",
        "description": "Clinical description with no identifying patient information. Verifies text is returned 100% unaltered with entity_count: 0.",
        "value": {
            "text": "Patient presented with acute dry cough, bilateral wheezing, and mild dyspnea. Prescribed albuterol inhaler 90mcg.",
            "org_id": "203674"
        }
    },
    "edge_case_missing_fields": {
        "summary": "5. Edge Case: Invalid Request (Missing both text & json_data)",
        "description": "Missing required fields, demonstrating HTTP 400 Bad Request validation response.",
        "value": {
            "org_id": "203674"
        }
    }
}

UNIFIED_ANONYMIZE_RESPONSE_EXAMPLES = {
    "text_mode_response": {
        "summary": "1. Text Mode Anonymized Response (200 OK)",
        "value": {
            "original_text": "Patient Elijah Fisher had severe anaphylaxis. Diagnosed by Dr. Robert Smith. Call 555-0199.",
            "anonymized_text": "Patient [PERSON_1] had severe anaphylaxis. Diagnosed by [PERSON_2]. Call [PHONE_1].",
            "entities": [
                {"entity": "NAME", "text": "Elijah Fisher", "start": 8, "end": 21, "confidence": 0.985, "category": "pii", "label": "Name"},
                {"entity": "NAME", "text": "Robert Smith", "start": 59, "end": 71, "confidence": 0.978, "category": "pii", "label": "Name"},
                {"entity": "PHONE", "text": "555-0199", "start": 78, "end": 86, "confidence": 0.992, "category": "pii", "label": "Phone"}
            ],
            "entity_count": 3
        }
    },
    "json_mode_response": {
        "summary": "2. JSON Mode Anonymized Response (200 OK)",
        "value": {
            "anonymized_data": {
                "patient_name": "GIVEN_c99d783c FAM_3a99f959",
                "phone": "PHONE_a61f1019",
                "diagnosis": "Type 2 diabetes mellitus"
            },
            "entity_count": 2,
            "mappings": [
                {"entity_type": "NAME", "original_value": "Elijah Fisher", "tokenized_value": "GIVEN_c99d783c FAM_3a99f959"},
                {"entity_type": "PHONE", "original_value": "555-234-5678", "tokenized_value": "PHONE_a61f1019"}
            ]
        }
    }
}

UNIFIED_RESTORE_REQUEST_EXAMPLES = {
    "mode_a_restore_text": {
        "summary": "1. Mode A: Restore Tokens in Clinical Text",
        "description": "Reverses surrogate tokens in a clinical narrative for doctor screen presentation.",
        "value": {
            "text": "Patient GIVEN_c99d783c FAM_3a99f959 diagnosed with Type 2 diabetes by [PERSON_35a29afa]",
            "org_id": "203674",
            "purpose": "patient_care"
        }
    },
    "mode_b_restore_tokens": {
        "summary": "2. Mode B: Restore Direct Token List",
        "description": "Passes an array of surrogate tokens to receive original cleartext values.",
        "value": {
            "tokens": ["FAM_3a99f959", "GIVEN_c99d783c", "PHONE_a61f1019"],
            "org_id": "203674",
            "purpose": "patient_care"
        }
    },
    "mode_c_restore_json": {
        "summary": "3. Mode C: Restore Structured JSON",
        "description": "Restores tokens embedded in any nested JSON object.",
        "value": {
            "json_data": {
                "patient": {
                    "name": "GIVEN_c99d783c FAM_3a99f959",
                    "phone": "PHONE_a61f1019"
                }
            },
            "org_id": "203674",
            "purpose": "patient_care"
        }
    },
    "edge_case_unknown_token": {
        "summary": "4. Edge Case: Non-Existent / Expired Token",
        "description": "Tests graceful fallback when a token is not in the vault (leaves surrogate token as-is without raising a 500 error).",
        "value": {
            "text": "Patient GIVEN_00000000 with unknown token",
            "org_id": "203674",
            "purpose": "patient_care"
        }
    }
}

UNIFIED_RESTORE_RESPONSE_EXAMPLES = {
    "text_restored": {
        "summary": "1. Text Restored (200 OK)",
        "value": {
            "restored_text": "Patient Elijah Fisher diagnosed with Type 2 diabetes by Dr. Sarah Connor"
        }
    },
    "tokens_restored": {
        "summary": "2. Token List Restored (200 OK)",
        "value": {
            "results": [
                {"tokenized_value": "FAM_3a99f959", "original_value": "Fisher", "entity_type": "FAMILY_NAME", "restored": True},
                {"tokenized_value": "GIVEN_c99d783c", "original_value": "Elijah", "entity_type": "GIVEN_NAME", "restored": True},
                {"tokenized_value": "PHONE_a61f1019", "original_value": "555-234-5678", "entity_type": "PHONE", "restored": True}
            ]
        }
    }
}

# ==============================================================================
# 3. RoBERTa PII Detection & Transformation Endpoints
# ==============================================================================

PREDICT_REQUEST_EXAMPLES = {
    "standard_predict": {
        "summary": "1. Standard Text Scan",
        "description": "Detects demographic PII entity boundaries and confidence scores.",
        "value": {
            "text": "Call patient Elijah Fisher at 555-234-5678 regarding prescription refill.",
            "min_confidence": 0.5
        }
    },
    "high_confidence_filter": {
        "summary": "2. High Confidence Filtering (min_confidence=0.9)",
        "description": "Drops marginal entity matches below 0.9 confidence threshold.",
        "value": {
            "text": "Elijah Fisher living on 123 Main Street Boston MA",
            "min_confidence": 0.9
        }
    }
}

PREDICT_RESPONSE_EXAMPLES = {
    "standard_predict_response": {
        "summary": "Entities Detected (200 OK)",
        "value": {
            "text": "Call patient Elijah Fisher at 555-234-5678 regarding prescription refill.",
            "entities": [
                {"entity": "NAME", "text": "Elijah Fisher", "start": 13, "end": 26, "confidence": 0.985, "category": "pii", "label": "Name"},
                {"entity": "PHONE", "text": "555-234-5678", "start": 30, "end": 42, "confidence": 0.992, "category": "pii", "label": "Phone"}
            ],
            "entity_count": 2,
            "contains_pii": True
        }
    }
}

BATCH_PREDICT_REQUEST_EXAMPLES = {
    "standard_batch": {
        "summary": "Batch Text Ingress",
        "description": "Array of multiple clinical text strings.",
        "value": {
            "texts": [
                "Patient Elijah Fisher arrived at 09:00 AM.",
                "Dr. Sarah Connor completed the consultation."
            ],
            "min_confidence": 0.6
        }
    }
}

VALIDATE_REQUEST_EXAMPLES = {
    "validate_any": {
        "summary": "1. General PII Presence Check",
        "description": "Verifies whether text contains any PII without mutating the string.",
        "value": {
            "text": "Patient Elijah Fisher email privacyds@mailinator.com",
            "min_confidence": 0.5
        }
    },
    "validate_restricted_types": {
        "summary": "2. Restricted Entity Filter (NAME only)",
        "description": "Checks only for specific entity types, ignoring others.",
        "value": {
            "text": "Patient Elijah Fisher email privacyds@mailinator.com",
            "entity_types": ["NAME"],
            "min_confidence": 0.5
        }
    }
}

VALIDATE_RESPONSE_EXAMPLES = {
    "validation_positive": {
        "summary": "PII Detected Response",
        "value": {
            "contains_pii": True,
            "entity_types_found": ["EMAIL", "NAME"],
            "entity_count": 2,
            "entities": [
                {"entity": "NAME", "text": "Elijah Fisher", "start": 8, "end": 21, "confidence": 0.985, "category": "pii", "label": "Name"},
                {"entity": "EMAIL", "text": "privacyds@mailinator.com", "start": 28, "end": 52, "confidence": 0.995, "category": "pii", "label": "Email"}
            ]
        }
    }
}

MASK_REQUEST_EXAMPLES = {
    "style_type": {
        "summary": "1. Mask Style: Type ([NAME])",
        "value": {
            "text": "Patient Elijah Fisher call 555-234-5678",
            "mask_style": "type",
            "min_confidence": 0.5
        }
    },
    "style_placeholder": {
        "summary": "2. Mask Style: Placeholder (<REDACTED>)",
        "value": {
            "text": "Patient Elijah Fisher call 555-234-5678",
            "mask_style": "placeholder",
            "min_confidence": 0.5
        }
    },
    "style_asterisk": {
        "summary": "3. Mask Style: Asterisk (********)",
        "value": {
            "text": "Patient Elijah Fisher call 555-234-5678",
            "mask_style": "asterisk",
            "min_confidence": 0.5
        }
    },
    "style_anonymize": {
        "summary": "4. Mask Style: Anonymize (Realistic Synthetic)",
        "value": {
            "text": "Patient Elijah Fisher call 555-234-5678",
            "mask_style": "anonymize",
            "min_confidence": 0.5
        }
    }
}

MASK_RESPONSE_EXAMPLES = {
    "style_type_response": {
        "summary": "1. Masked with Type ([NAME], [PHONE])",
        "value": {
            "original_text": "Patient Elijah Fisher call 555-234-5678",
            "masked_text": "Patient [NAME] call [PHONE]",
            "entities_masked": 2,
            "entities": [
                {"entity": "NAME", "text": "Elijah Fisher", "start": 8, "end": 21, "confidence": 0.985, "category": "pii", "label": "Name"},
                {"entity": "PHONE", "text": "555-234-5678", "start": 27, "end": 39, "confidence": 0.992, "category": "pii", "label": "Phone"}
            ]
        }
    }
}

# ==============================================================================
# 4. Clinical PHI Detection Endpoints (/phi/*)
# ==============================================================================

PHI_PREDICT_REQUEST_EXAMPLES = {
    "standard_clinical_progress_note": {
        "summary": "1. Clinical Progress Note (HIPAA 18 PHI)",
        "description": "Unstructured clinician narrative containing dates, ages, medical record number, and clinician signature.",
        "value": {
            "text": "Patient John Doe, 45-year-old male, admitted on 10/12/2023 with chest pain. MRN: 948201. Attending: Dr. Gregory House.",
            "min_confidence": 0.5
        }
    }
}

PHI_PREDICT_RESPONSE_EXAMPLES = {
    "phi_detected_response": {
        "summary": "Clinical PHI Entities Detected",
        "value": {
            "text": "Patient John Doe, 45-year-old male, admitted on 10/12/2023 with chest pain. MRN: 948201. Attending: Dr. Gregory House.",
            "entities": [
                {"entity": "PATIENT_NAME", "text": "John Doe", "start": 8, "end": 16, "confidence": 0.99, "category": "phi", "label": "Patient Name"},
                {"entity": "DATE", "text": "10/12/2023", "start": 48, "end": 58, "confidence": 0.98, "category": "phi", "label": "Date"},
                {"entity": "MRN", "text": "948201", "start": 82, "end": 88, "confidence": 0.99, "category": "phi", "label": "Medical Record Number"},
                {"entity": "DOCTOR_NAME", "text": "Dr. Gregory House", "start": 101, "end": 118, "confidence": 0.99, "category": "phi", "label": "Doctor Name"}
            ],
            "entity_count": 4,
            "contains_phi": True,
            "backend": "openai"
        }
    }
}

PHI_ANONYMIZE_REQUEST_EXAMPLES = {
    "standard_phi_anonymize": {
        "summary": "Clinical Narrative Anonymization",
        "description": "Detects and replaces HIPAA 18 identifiers in unstructured clinical notes.",
        "value": {
            "text": "Patient John Doe admitted to Boston General Hospital on 2023-10-12 by Dr. House.",
            "mask_style": "type",
            "min_confidence": 0.5
        }
    }
}

PHI_ANONYMIZE_RESPONSE_EXAMPLES = {
    "phi_anonymized_response": {
        "summary": "Clinical Narrative Anonymized with PHI Mappings",
        "value": {
            "anonymized_text": "Patient [PATIENT_NAME] admitted to [HOSPITAL] on [DATE] by [DOCTOR_NAME].",
            "mappings": [
                {"entity_type": "PATIENT_NAME", "label": "Patient Name", "original_value": "John Doe", "tokenized_value": "[PATIENT_NAME]", "policy_applied": "anonymize"},
                {"entity_type": "HOSPITAL", "label": "Hospital", "original_value": "Boston General Hospital", "tokenized_value": "[HOSPITAL]", "policy_applied": "anonymize"},
                {"entity_type": "DATE", "label": "Date", "original_value": "2023-10-12", "tokenized_value": "[DATE]", "policy_applied": "anonymize"},
                {"entity_type": "DOCTOR_NAME", "label": "Doctor Name", "original_value": "Dr. House", "tokenized_value": "[DOCTOR_NAME]", "policy_applied": "anonymize"}
            ],
            "entity_count": 4,
            "backend": "openai"
        }
    }
}

# ==============================================================================
# 5. System Health & Observability Endpoints (/health, /ready)
# ==============================================================================

HEALTH_RESPONSE_EXAMPLES = {
    "healthy_service": {
        "summary": "Healthy Service (200 OK)",
        "value": {
            "status": "ok",
            "model_loaded": True,
            "device": "cpu",
            "domain": "dev-pdsapi.hekma.ai",
            "storage_backend": "postgresql",
            "detail": None,
            "phi_ready": True,
            "phi_backend": "openai"
        }
    }
}

READINESS_RESPONSE_EXAMPLES = {
    "service_ready": {
        "summary": "Service Ready (200 OK)",
        "value": {
            "ready": True,
            "model_warm": True,
            "database_connected": True,
            "storage_backend": "postgresql",
            "details": None
        }
    }
}

# Common Error Responses
BATCH_PREDICT_RESPONSE_EXAMPLES = {
    "standard_batch_response": {
        "summary": "Batch Results",
        "value": {
            "results": [
                {
                    "text": "Patient Elijah Fisher arrived at 09:00 AM.",
                    "entities": [{"entity": "NAME", "text": "Elijah Fisher", "start": 8, "end": 21, "confidence": 0.985, "category": "pii", "label": "Name"}],
                    "entity_count": 1,
                    "contains_pii": True
                },
                {
                    "text": "Dr. Sarah Connor completed the consultation.",
                    "entities": [{"entity": "NAME", "text": "Sarah Connor", "start": 4, "end": 16, "confidence": 0.975, "category": "pii", "label": "Name"}],
                    "entity_count": 1,
                    "contains_pii": True
                }
            ]
        }
    }
}

ANONYMIZE_API_REQUEST_EXAMPLES = {
    "standard_middleware_request": {
        "summary": "Raw Text Ingress",
        "description": "Processes text via AnonymizationMiddleware, returning tokenized mappings.",
        "value": {
            "text": "Patient Elijah Fisher at 555-234-5678"
        }
    }
}

ANONYMIZE_API_RESPONSE_EXAMPLES = {
    "standard_middleware_response": {
        "summary": "Middleware Anonymization Result",
        "value": {
            "anonymized_text": "Patient [PERSON] at [PHONE_NUMBER]",
            "mappings": [
                {"entity_type": "PERSON", "original_value": "Elijah Fisher", "tokenized_value": "NAME_ddf92da1", "policy_applied": "anonymize"},
                {"entity_type": "PHONE", "original_value": "555-234-5678", "tokenized_value": "PHONE_c1892b89", "policy_applied": "anonymize"}
            ]
        }
    }
}

INTERNAL_RESTORE_REQUEST_EXAMPLES = {
    "standard_restore_tokens": {
        "summary": "Vault Direct Token Query",
        "description": "Internal direct query to token vault for array of tokens.",
        "value": {
            "tokenized_values": ["FAM_3a99f959", "GIVEN_c99d783c"],
            "org_id": "203674",
            "requester_id": "user-4821",
            "ip_address": "127.0.0.1",
            "purpose": "patient_care"
        }
    }
}

INTERNAL_RESTORE_RESPONSE_EXAMPLES = {
    "standard_restore_results": {
        "summary": "Restored Mappings",
        "value": {
            "results": [
                {"original_value": "Fisher", "tokenized_value": "FAM_3a99f959", "entity_type": "PERSON", "restored": True},
                {"original_value": "Elijah", "tokenized_value": "GIVEN_c99d783c", "entity_type": "PERSON", "restored": True}
            ]
        }
    }
}

INTERNAL_RESTORE_TEXT_REQUEST_EXAMPLES = {
    "standard_restore_text": {
        "summary": "Internal Text String Restoration",
        "value": {
            "text": "Patient GIVEN_c99d783c FAM_3a99f959 diagnosed with diabetes",
            "org_id": "203674",
            "requester_id": "user-4821",
            "ip_address": "127.0.0.1",
            "purpose": "patient_care"
        }
    }
}

INTERNAL_RESTORE_TEXT_RESPONSE_EXAMPLES = {
    "standard_restored_text": {
        "summary": "Restored Cleartext",
        "value": {
            "restored_text": "Patient Elijah Fisher diagnosed with diabetes"
        }
    }
}

ENTITIES_RESPONSE_EXAMPLES = {
    "supported_entities": {
        "summary": "18 Fine-Tuned Entity Types",
        "value": {
            "entity_types": ["CITY", "COUNTY", "DATE_TIME", "DOCTOR_NAME", "EMAIL", "FAMILY_NAME", "GIVEN_NAME", "HOSPITAL", "IDENTIFIER", "IP_ADDRESS", "LOCATION", "MEDICAL_RECORD_NUMBER", "NAME", "ORGANIZATION", "PATIENT_ID", "PHONE", "STATE", "STREET_ADDRESS", "URL", "ZIP_CODE"],
            "count": 20
        }
    }
}

INFO_RESPONSE_EXAMPLES = {
    "service_metadata": {
        "summary": "Microservice Runtime Information",
        "value": {
            "name": "PII / PHI Security Microservice",
            "version": "2.0.0",
            "description": "Production-grade PII & Clinical PHI Anonymization & Reverse Tokenization Layer",
            "supported_entity_types": 20,
            "phi_entity_types": 18,
            "endpoints": ["/health", "/ready", "/predict", "/validate", "/mask", "/anonymize", "/restore", "/api/v1/anonymize/fhir"]
        }
    }
}

PHI_HEALTH_RESPONSE_EXAMPLES = {
    "phi_ready": {
        "summary": "PHI Detector Health",
        "value": {
            "status": "ok",
            "phi_ready": True,
            "backend": "openai",
            "model": "gpt-4o-mini",
            "detail": None
        }
    }
}

PHI_ENTITIES_RESPONSE_EXAMPLES = {
    "phi_types": {
        "summary": "HIPAA 18 PHI Entity Types",
        "value": {
            "entity_types": [
                {"entity": "PATIENT_NAME", "label": "Patient Name", "description": "Full name or parts of patient names", "category": "phi"},
                {"entity": "DATE", "label": "Date", "description": "Admission, discharge, treatment dates", "category": "phi"},
                {"entity": "MRN", "label": "Medical Record Number", "description": "Hospital record identifiers", "category": "phi"},
                {"entity": "DOCTOR_NAME", "label": "Doctor Name", "description": "Attending or referring clinician names", "category": "phi"}
            ],
            "count": 4,
            "backend": "openai"
        }
    }
}

PHI_VALIDATE_REQUEST_EXAMPLES = {
    "standard_phi_validate": {
        "summary": "Check for PHI in Note",
        "value": {
            "text": "Patient Jane Doe seen on 2023-11-04 by Dr. Adams.",
            "min_confidence": 0.5
        }
    }
}

PHI_VALIDATE_RESPONSE_EXAMPLES = {
    "phi_found": {
        "summary": "Validation Result (PHI Detected)",
        "value": {
            "contains_phi": True,
            "entity_types_found": ["DATE", "DOCTOR_NAME", "PATIENT_NAME"],
            "entity_count": 3,
            "entities": [
                {"entity": "PATIENT_NAME", "text": "Jane Doe", "start": 8, "end": 16, "confidence": 0.99, "category": "phi", "label": "Patient Name"},
                {"entity": "DATE", "text": "2023-11-04", "start": 25, "end": 35, "confidence": 0.98, "category": "phi", "label": "Date"},
                {"entity": "DOCTOR_NAME", "text": "Dr. Adams", "start": 39, "end": 48, "confidence": 0.99, "category": "phi", "label": "Doctor Name"}
            ],
            "backend": "openai"
        }
    }
}

PHI_MASK_REQUEST_EXAMPLES = {
    "standard_phi_mask": {
        "summary": "Mask Clinical Note",
        "value": {
            "text": "Patient Jane Doe seen on 2023-11-04 by Dr. Adams.",
            "mask_style": "type",
            "min_confidence": 0.5
        }
    }
}

PHI_MASK_RESPONSE_EXAMPLES = {
    "phi_masked": {
        "summary": "Masked Result",
        "value": {
            "original_text": "Patient Jane Doe seen on 2023-11-04 by Dr. Adams.",
            "masked_text": "Patient [PATIENT_NAME] seen on [DATE] by [DOCTOR_NAME].",
            "entities_masked": 3,
            "entities": [
                {"entity": "PATIENT_NAME", "text": "Jane Doe", "start": 8, "end": 16, "confidence": 0.99, "category": "phi", "label": "Patient Name"}
            ],
            "backend": "openai"
        }
    }
}

PHI_BATCH_PREDICT_REQUEST_EXAMPLES = {
    "batch_progress_notes": {
        "summary": "Batch Clinical Progress Notes",
        "value": {
            "texts": [
                "Patient John Doe admitted with fever on 2023-10-12.",
                "Dr. Gregory House discharged patient on 2023-10-15."
            ],
            "min_confidence": 0.5
        }
    }
}

PHI_BATCH_PREDICT_RESPONSE_EXAMPLES = {
    "batch_results": {
        "summary": "Batch PHI Predictions",
        "value": {
            "results": [
                {"text": "Patient John Doe admitted with fever on 2023-10-12.", "entities": [{"entity": "PATIENT_NAME", "text": "John Doe", "start": 8, "end": 16, "confidence": 0.99, "category": "phi", "label": "Patient Name"}], "entity_count": 1, "contains_phi": True, "backend": "openai"},
                {"text": "Dr. Gregory House discharged patient on 2023-10-15.", "entities": [{"entity": "DOCTOR_NAME", "text": "Dr. Gregory House", "start": 0, "end": 17, "confidence": 0.99, "category": "phi", "label": "Doctor Name"}], "entity_count": 1, "contains_phi": True, "backend": "openai"}
            ],
            "backend": "openai"
        }
    }
}

# Common Error Responses
ERROR_400_BAD_REQUEST = {
    "description": "Bad Request — Invalid or Missing Parameters",
    "content": {
        "application/json": {
            "example": {"detail": "Must provide either 'text' or 'json_data'"}
        }
    }
}

ERROR_422_UNPROCESSABLE = {
    "description": "Validation Error — Malformed Schema or Field Constraints",
    "content": {
        "application/json": {
            "example": {
                "detail": [
                    {
                        "loc": ["body", "resource"],
                        "msg": "field required",
                        "type": "value_error.missing"
                    }
                ]
            }
        }
    }
}

ERROR_503_NOT_READY = {
    "description": "Service Unavailable — RoBERTa Model Initializing or DB Disconnected",
    "content": {
        "application/json": {
            "example": {
                "detail": "Service Not Ready (model_warm=False, db_connected=False)"
            }
        }
    }
}
