from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict

from api.services.fhir_anonymizer import fhir_anonymizer
from api.services.restorer import restorer, RestoreRequest
from api.openapi_examples import (
    FHIR_ANONYMIZE_REQUEST_EXAMPLES,
    FHIR_ANONYMIZE_RESPONSE_EXAMPLES,
    FHIR_BATCH_REQUEST_EXAMPLES,
    FHIR_BATCH_RESPONSE_EXAMPLES,
    GENERIC_JSON_REQUEST_EXAMPLES,
    RESTORE_JSON_REQUEST_EXAMPLES,
    ERROR_422_UNPROCESSABLE,
)

structured_router = APIRouter(tags=["1. FHIR & Structured Ingress"])


class FHIRAnonymizeRequest(BaseModel):
    resource: Dict[str, Any] = Field(..., description="FHIR Resource or Bundle JSON")
    org_id: str = Field(default="default", description="Tenant Organization ID")

    model_config = ConfigDict(
        json_schema_extra={
            "example": FHIR_ANONYMIZE_REQUEST_EXAMPLES["patient_demographics"]["value"]
        }
    )


class FHIRAnonymizeResponse(BaseModel):
    anonymized_resource: Dict[str, Any]
    mappings_count: int
    mappings: List[Dict[str, Any]]

    model_config = ConfigDict(
        json_schema_extra={
            "example": FHIR_ANONYMIZE_RESPONSE_EXAMPLES["patient_demographics_response"]["value"]
        }
    )


class FHIRBatchAnonymizeRequest(BaseModel):
    resources: List[Dict[str, Any]] = Field(..., description="List of FHIR resources")
    org_id: str = Field(default="default", description="Tenant Organization ID")

    model_config = ConfigDict(
        json_schema_extra={
            "example": FHIR_BATCH_REQUEST_EXAMPLES["standard_clinical_bundle"]["value"]
        }
    )


class FHIRBatchAnonymizeResponse(BaseModel):
    anonymized_resources: List[Dict[str, Any]]
    total_mappings_count: int

    model_config = ConfigDict(
        json_schema_extra={
            "example": FHIR_BATCH_RESPONSE_EXAMPLES["standard_batch_response"]["value"]
        }
    )


class JSONRestoreRequest(BaseModel):
    data: Any = Field(..., description="Arbitrary JSON structure with tokens to restore")
    org_id: str = Field(default="default")
    purpose: str = Field(default="patient_care")

    model_config = ConfigDict(
        json_schema_extra={
            "example": RESTORE_JSON_REQUEST_EXAMPLES["standard_restore_json"]["value"]
        }
    )


async def get_current_user(request: Request) -> str:
    api_key = request.headers.get("x-api-key")
    if not api_key:
        return "system-anonymous"
    return f"user-{abs(hash(api_key)) % 10000}"


@structured_router.post(
    "/api/v1/anonymize/fhir",
    response_model=FHIRAnonymizeResponse,
    responses={
        200: {
            "description": "FHIR Resource Successfully Anonymized (LOINC/ICD-10/SNOMED Preserved)",
            "content": {
                "application/json": {
                    "examples": FHIR_ANONYMIZE_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def anonymize_fhir(
    payload: FHIRAnonymizeRequest = Body(
        ...,
        openapi_examples=FHIR_ANONYMIZE_REQUEST_EXAMPLES
    )
):
    """Recursively anonymizes a FHIR resource or Bundle, preserving LOINC/SNOMED/RxNorm codes."""
    try:
        anon_resource, mappings = await fhir_anonymizer.anonymize_fhir_resource(
            payload.resource, org_id=payload.org_id
        )
        return FHIRAnonymizeResponse(
            anonymized_resource=anon_resource,
            mappings_count=len(mappings),
            mappings=[
                {
                    "entity_type": m.entity_type,
                    "original_value": m.original_value,
                    "tokenized_value": m.tokenized_value,
                }
                for m in mappings
            ],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FHIR Anonymization failed: {e}") from e


@structured_router.post(
    "/api/v1/anonymize/fhir/batch",
    response_model=FHIRBatchAnonymizeResponse,
    responses={
        200: {
            "description": "Batch Clinical Resources Anonymized",
            "content": {
                "application/json": {
                    "examples": FHIR_BATCH_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def anonymize_fhir_batch(
    payload: FHIRBatchAnonymizeRequest = Body(
        ...,
        openapi_examples=FHIR_BATCH_REQUEST_EXAMPLES
    )
):
    """Batch-anonymizes multiple FHIR resources in a single high-throughput request."""
    try:
        anon_list = []
        total_mappings = 0
        for res in payload.resources:
            anon_res, mappings = await fhir_anonymizer.anonymize_fhir_resource(
                res, org_id=payload.org_id
            )
            anon_list.append(anon_res)
            total_mappings += len(mappings)
        return FHIRBatchAnonymizeResponse(
            anonymized_resources=anon_list,
            total_mappings_count=total_mappings,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"FHIR Batch Anonymization failed: {e}") from e


@structured_router.post(
    "/api/v1/anonymize/json",
    response_model=FHIRAnonymizeResponse,
    responses={
        200: {
            "description": "Generic JSON Anonymized",
            "content": {
                "application/json": {
                    "examples": FHIR_ANONYMIZE_RESPONSE_EXAMPLES
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def anonymize_generic_json(
    payload: FHIRAnonymizeRequest = Body(
        ...,
        openapi_examples=GENERIC_JSON_REQUEST_EXAMPLES
    )
):
    """Anonymizes arbitrary JSON records by scanning identifying strings."""
    return await anonymize_fhir(payload)


@structured_router.post(
    "/internal/restore-json",
    tags=["4. Reverse Tokenization & Token Vault"],
    responses={
        200: {
            "description": "JSON Tokens Successfully Restored",
            "content": {
                "application/json": {
                    "example": {
                        "restored_data": {
                            "patient": {
                                "id": "203674",
                                "name": "Elijah Fisher",
                                "phone": "555-234-5678"
                            },
                            "clinical_summary": "Type 2 diabetes managed by Dr. Sarah Connor"
                        }
                    }
                }
            }
        },
        422: ERROR_422_UNPROCESSABLE,
    }
)
async def restore_json(
    payload: JSONRestoreRequest = Body(
        ...,
        openapi_examples=RESTORE_JSON_REQUEST_EXAMPLES
    ),
    request: Request = None,
    current_user: str = Depends(get_current_user),
):
    """Restores tokens inside nested JSON objects for authorized clinical display."""
    client_ip = request.client.host if (request and request.client) else "127.0.0.1"
    restored_data = await restorer.restore_in_json(
        payload.data,
        org_id=payload.org_id,
        requester_id=current_user,
        purpose=payload.purpose,
        ip=client_ip,
    )
    return {"restored_data": restored_data}
