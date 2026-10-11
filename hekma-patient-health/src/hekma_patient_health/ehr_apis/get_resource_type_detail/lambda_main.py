#from ...awsutils.elasticsearch_utils import ElasticSearchConnection
# from ...awsutils.postgresql_utils import get_pg_connection, release_pg_connection

from ...awsutils.postgresql_utils import pg_transaction


import json
import os
import copy
import boto3
from botocore.config import Config
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

_mapping_json_cache = None
def get_mapping_json():
    global _mapping_json_cache
    if _mapping_json_cache is None:
        file_path = BASE_DIR / "integrate.json"
        with open(file_path, "r") as f:
            _mapping_json_cache = json.loads(f.read())
    return _mapping_json_cache

_lab_references_cache = None
def get_lab_references():
    global _lab_references_cache
    if _lab_references_cache is None:
        file_path = BASE_DIR / "lab_references.json"
        with open(file_path, "r") as f:
            _lab_references_cache = json.loads(f.read())
    return _lab_references_cache

from ...redis_service import *
import traceback
from ...awsutils.mysql_db_connection import mysql_connection
from ..ctms_patient_ids import (
    BLANK_IDENTIFIERS,
    append_id_only_scope,
    build_ctms_sql,
    normalize_identifier,
    resolve_chart_patient_id,
    resolve_ctms_patient_ids,
)
from ..fhir_source_filters import (
    EHR_SOURCE_PREDICATE,
    INTERNAL_TO_MODULE,
    to_internal_dashboard_row,
)
from ..bmi_rows import fetch_bmi_dashboard_rows


# Clients send the literal strings "undefined"/"null" when an id is missing. They must
# never reach a WHERE clause: some Patient rows hold 'undefined' in subjectId, so
# matching on it returns an unrelated patient's records.
# (BLANK_IDENTIFIERS / normalize_identifier / resolve_ctms_patient_ids live in ctms_patient_ids.py)


#os.environ["DISABLE_REDIS"] = "Y"


es_index_map = {
        "Patient": {"index": "patient"},
        "AllergyIntolerance": {"index": "allergy",
                               "patient_field": "patient.reference.keyword",
                               "sort_field": "onset",
                               "_source1": ["substance", "criticality", "onset", "category", "status", "id"],
                               "mobile_source":  ["status", "substance.text", "patient", "onset", "criticality",
                                                  "category"],
                               "active": {
                                   "status": "active"
                               }

                               },
        "Immunization": {"index": "immunization",
                         "patient_field": "patient.reference.keyword",
                         "sort_field": "date",
                         "_source1": ["occurrenceDateTime", "date", "wasNotGiven", "vaccineCode", "reported", "status", "id"],
                         "mobile_source": ["occurrenceDateTime", "status", "vaccineCode.text", "date",  "doseQuantity","patient"]
                         },
        "Condition": {"index": "condition",
                      "patient_field": "patient.reference.keyword",
                      "sort_field": "onsetDateTime",
                      "_source1": ["code", "text", "verificationStatus", "clinicalStatus", "onsetDateTime", "id",
                                  "category",
                                  "dateRecorded"],
                      "mobile_source": ["code.text","patient","clinicalStatus","onsetDateTime"],
                      "active": {
                                   "clinicalStatus": "active"
                               }
                      },
        "MedicationOrder": {"index": "medication_order",
                            "patient_field": "patient.reference.keyword",
                            "sort_field": "dateWritten",
                            "_source1": ["medicationCodeableConcept", "dateWritten", "dosageInstruction", "id",
                                        "status"],
                            "mobile_source": ["medicationCodeableConcept.text", "dateWritten" ,"status", "patient"],
                            "active": {
                                   "status": "active"
                               }
                            },
        "Observation": {"index": "observation",
                        "patient_field": "subject.reference.keyword",
                        "sort_field": "meta.lastUpdated",
                        "mobile_source": ["status","valueQuantity","code.text", "effectiveDateTime","subject.reference", "category"]
                        },
        "Procedure": {"index": "procedure",
                      "patient_field": "subject.reference.keyword",
                      "sort_field": "meta.lastUpdated"
                      },
"fastenhealth_condition": {
    "index": "fastenhealth_condition",
    "patient_field": "patient_id",  
    "mobile_source": ["code.text","subject","clinicalStatus","onsetDateTime"],
    "sort_field": "sort_date"
},

"fastenhealth_immunization": {
    "index": "fastenhealth_immunization",
    "patient_field": "patient_id",
    "mobile_source": ["occurrenceDateTime", "status", "vaccineCode.text", "date",  "doseQuantity","patient"],
    "sort_field": "sort_date"
},
"fastenhealth_observation": {
    "index": "fastenhealth_observation",
    "patient_field": "patient_id",
    "mobile_source": ["status","valueQuantity","code.text", "effectiveDateTime","subject.reference", "category"],
    "sort_field": "sort_date"
},
"fastenhealth_procedure": {
    "index": "fastenhealth_procedure",
    "patient_field": "patient_id",
    "mobile_source": ["resourceType","id","meta", "status", "code", "subject", "encounter", "performedPeriod", "location"],
    "sort_field": "sort_date"
},
"fastenhealth_allergyintolerance": {
    "index": "fastenhealth_allergyintolerance",
    "patient_field": "patient_id",
    "mobile_source":  ["status", "substance.text", "patient", "onset", "criticality", "category"],
    "sort_field": "sort_date"
},
"fastenhealth_medicationorder": {
    "index": "fastenhealth_medicationrequest",
    "patient_field": "patient_id",
    "sort_field": "authoredOn"
}





    }
"""
        "DiagnosticReport": {"index": "lab_result",
                             "patient_field": "subject.reference.keyword",
                             "sort_field": "effectiveDateTime",
                             "_source1": ["code", "result", "effectiveDateTime", "id", "category", "issued",
                                         "status"]},
        "MedicationStatement": {"index": "medication_statement",
                                "patient_field": "patient.reference.keyword",
                                "sort_field": "meta.lastUpdated"
                                },
   "RelatedPerson": {"index": "related_person",
                          "patient_field": "patient.reference.keyword",
                          "sort_field": "meta.lastUpdated"
                          },
            "CarePlan": {"index": "care_plan",
                     "patient_field": "subject.reference.keyword",
                     "sort_field": "meta.lastUpdated"
                     },
        "Claim": {"index": "claim",
                  "patient_field": "patient.reference.keyword",
                  "sort_field": "meta.lastUpdated"
                  },
        "Encounter": {"index": "encounter",
                      "patient_field": "patient.reference.keyword",
                      "sort_field": "meta.lastUpdated"
                      },
        "ImagingStudy": {"index": "imaging_study",
                         "patient_field": "patient.reference.keyword",
                         "sort_field": "meta.lastUpdated"
                         },
        
        
        "ImagingStudy_CMS":{"index":"imagingstudy_cms",
                     "patient_field": "subject.reference.keyword"},

        "MedicationStatement_CMS":{"index":"medicationstatement_cms",
                     "patient_field": "subject.reference.keyword"},
        "RelatedPerson_CMS":{"index":"relatedperson_cms",
                     "patient_field": "subject.reference.keyword"},
"""

"""
        "Goal": {"index": "goal",
                 "patient_field": "subject.reference.keyword",
                 "sort_field": "lastUpdated"
                 },
        "Location": {"index": "location",
                     "patient_field": "subject.reference.keyword",
                     "sort_field": "lastUpdated"
                     },
        "Organization": {"index": "organization",
                         "patient_field": "subject.reference.keyword",
                         "sort_field": "lastUpdated"
                         },
        "Medication": {"index": "medication",
                       "patient_field": "subject.reference.keyword",
                       "sort_field": "lastUpdated"
                       },
        "Practitioner": {"index": "practitioner",
                        "patient_field": "subject.reference.keyword",
                        "sort_field": "lastUpdated"
                        }
        ,"""


# def get_data(index, body, event_type: str = None):
#     es = ElasticSearchConnection()
#     response = es.search(index=index, body=body)
#     data = dict()
#     data['data'] = []
#     for d in response['hits']['hits']:
#         source = d['_source']
#         if event_type == "Immunization":
#             if 'occurrenceDateTime' in source:
#                 source['date'] = source['occurrenceDateTime']
#         elif event_type == "Observation":
#             if 'category' in source and isinstance(source['category'], list):
#                 if len(source['category']) > 0:
#                     source['category'] = source['category'][0]
#                 else:
#                     source['category'] = dict()
#         data['data'].append(source)
#     data['total'] = response['hits']['total']['value']
#     data['size'] = len(data['data'])
#     return data


import re

_LOINC_SYSTEM = "http://loinc.org"
_CATALOG_EXTENSION_URL = "https://hekma.ai/fhir/StructureDefinition/catalog"


def _catalog_extension_values(resource):
    field_key = None
    panel = None
    for ext in resource.get("extension") or []:
        if not isinstance(ext, dict) or ext.get("url") != _CATALOG_EXTENSION_URL:
            continue
        for nested in ext.get("extension") or []:
            if not isinstance(nested, dict):
                continue
            if nested.get("url") == "fieldKey":
                field_key = nested.get("valueString") or field_key
            elif nested.get("url") == "panel":
                panel = nested.get("valueString") or panel
    return field_key, panel


def normalize_observation_for_cms(resource):

    # 1. Name
    code = resource.get("code", {})
    name = None

    if isinstance(code, dict):
        name = code.get("text")
        if not name:
            coding = code.get("coding", [])
            if isinstance(coding, list) and coding:
                name = coding[0].get("display") or coding[0].get("code")

    if name:
        resource["Name"] = name

    coding = code.get("coding") if isinstance(code, dict) else None
    if isinstance(coding, list):
        for item in coding:
            if (
                isinstance(item, dict)
                and item.get("system") == _LOINC_SYSTEM
                and item.get("code")
            ):
                resource["loincCode"] = item.get("code")
                break

    field_key, panel = _catalog_extension_values(resource)
    if field_key:
        resource["fieldKey"] = field_key
    if panel:
        resource["catalogCategory"] = panel

    # 2. Status
    resource["Status"] = resource.get("status", "unknown")

    # 3. Date Handling
    date_value = (
        resource.get("effectiveDateTime")
        or resource.get("effectivePeriod", {}).get("start")
        or resource.get("effectivePeriod", {}).get("end")
        or resource.get("issued")
        or resource.get("meta", {}).get("lastUpdated")
    )

    if date_value:
        resource["date_of_observation"] = date_value[:10]
        resource["sort_date"] = date_value[:10]

    # ---- 4. Category ----
    category = resource.get("category")

    if isinstance(category, list) and category:
        cat = category[0]

        # Keep original category structure intact
        resource["category_text"] = cat.get("text", "unknown")

        coding = cat.get("coding", [])
        if isinstance(coding, list) and coding:
            resource["category_code"] = coding[0].get("code")
        else:
            resource["category_code"] = None

    else:
        # Do NOT overwrite original category
        resource["category_text"] = "unknown"
        resource["category_code"] = None
        
    # 5. ValueQuantity (Direct)
    if "valueQuantity" in resource:
        resource["value_quantity"] = resource["valueQuantity"]

    # 6. Convert valueString → valueQuantity
    elif "valueString" in resource:
        vs = resource["valueString"]

        match = re.match(r"^\s*([\d.]+)[\s\-]*([a-zA-Z/]+)\s*$", vs)
        if match:
            value = float(match.group(1))
            unit = match.group(2)

            resource["value_quantity"] = {
                "value": value,
                "unit": unit
            }
        else:
            resource["optionalvs_result_text"] = vs

    # 7. valueCodeableConcept
    if "valueCodeableConcept" in resource:
        vcc = resource["valueCodeableConcept"]
        if isinstance(vcc, dict):
            text = vcc.get("text")
            if text:
                resource["optional_result_text"] = text

    # 8. Component Handling
    components = resource.get("component")
    if isinstance(components, list) and components:
        first = components[0]

        if "code" in first:
            resource["result_text"] = first["code"].get("text")

        if "valueQuantity" in first:
            resource["optional_value_quantity"] = first["valueQuantity"]

    return resource


def normalize_medication_for_cms(resource):

    # Normalize Medication Name (FHIR-safe)

    name = None

    # Case 1: medicationCodeableConcept
    mcc = resource.get("medicationCodeableConcept")
    if isinstance(mcc, dict):
        name = mcc.get("text")
        if not name:
            coding = mcc.get("coding")
            if isinstance(coding, list) and coding:
                name = coding[0].get("display") or coding[0].get("code")

    # Case 2: medicationReference
    if not name:
        mref = resource.get("medicationReference")
        if isinstance(mref, dict):

            # Prefer display
            name = mref.get("display")

            # If no display → extract ID from reference
            if not name:
                reference = mref.get("reference")
                if isinstance(reference, str) and "/" in reference:
                    name = reference.split("/")[-1]

    # Final fallback
    if not name:
        name = "Unknown"

    # Guarantee structure for integrate.json mapping
    resource["medicationCodeableConcept"] = {
        "text": name
    }

    # Normalize dateWritten

    date_written = None

    authored = resource.get("authoredOn")
    if isinstance(authored, str):
        date_written = authored[:10]

    # Fallback → meta.lastUpdated
    if not date_written:
        meta_date = resource.get("meta", {}).get("lastUpdated")
        if isinstance(meta_date, str):
            date_written = meta_date[:10]

    # Final safe fallback → stable historical date
    if not date_written:
        date_written = "1900-01-01"

    resource["dateWritten"] = date_written
    resource["sort_date"] = date_written

    # Normalize dateEnded

    date_ended = None

    # Case A: dosageInstruction → boundsPeriod.end
    dosage = resource.get("dosageInstruction")
    if isinstance(dosage, list) and dosage:
        bounds = (
            dosage[0]
            .get("timing", {})
            .get("repeat", {})
            .get("boundsPeriod", {})
        )
        end = bounds.get("end")
        if isinstance(end, str):
            date_ended = end[:10]

    # Case B: dispenseRequest → validityPeriod.end
    if not date_ended:
        validity = resource.get("dispenseRequest", {}).get("validityPeriod", {})
        end = validity.get("end")
        if isinstance(end, str):
            date_ended = end[:10]

    # Fallback → meta.lastUpdated
    if not date_ended:
        meta_date = resource.get("meta", {}).get("lastUpdated")
        if isinstance(meta_date, str):
            date_ended = meta_date[:10]

    # Final fallback: only use dateWritten if inactive/completed, not for active medications
    status_val = str(resource.get("status") or "").lower()
    if not date_ended and status_val not in ("active", ""):
        date_ended = date_written

    resource["dateEnded"] = date_ended

    # Normalize Status
    resource["status"] = resource.get("status", "unknown")

    return resource

def normalize_allergy_for_cms(resource):

    # ---- 1. Substance ----
    substance_text = None
    code = resource.get("code", {})

    if isinstance(code, dict):
        substance_text = code.get("text")
        if not substance_text:
            coding = code.get("coding", [])
            if isinstance(coding, list) and coding:
                substance_text = coding[0].get("display") or coding[0].get("code")

    if substance_text:
        resource["substance"] = {"text": substance_text}

    # ---- 2. Status ----
    status_value = None

    clinical = resource.get("clinicalStatus")
    if isinstance(clinical, dict):
        coding = clinical.get("coding", [])
        if isinstance(coding, list) and coding:
            status_value = coding[0].get("code")

    if not status_value:
        verification = resource.get("verificationStatus")
        if isinstance(verification, dict):
            coding = verification.get("coding", [])
            if isinstance(coding, list) and coding:
                status_value = coding[0].get("code")

    resource["status"] = status_value if status_value else "unknown"

    # ---- 3. Category ----
    category = resource.get("category")
    if isinstance(category, list) and category:
        resource["category"] = category[0]
    else:
        resource["category"] = "unknown"

    # ---- 4. Criticality / severity ----
    from ...services.clinical_fhir.mappers import read_allergy_severity_from_fhir

    severity = read_allergy_severity_from_fhir(resource)
    resource["severity"] = severity
    resource["criticality"] = severity

    # ---- 5. Onset ----
    onset_value = resource.get("onsetDateTime")
    if not onset_value:
        for ext in resource.get("extension") or []:
            if isinstance(ext, dict) and "ctms-payload" in str(ext.get("url")):
                try:
                    payload = json.loads(ext.get("valueString") or "{}")
                    onset_value = payload.get("onsetDate") or payload.get("startDate")
                except Exception:
                    pass
    if not onset_value:
        onset_value = (
            resource.get("recordedDate")
            or resource.get("meta", {}).get("lastUpdated")
        )

    if onset_value:
        resource["onset"] = onset_value
        resource["sort_date"] = onset_value[:10]
    else:
        resource["sort_date"] = "1970-01-01"

    return resource


def normalize_procedure_for_cms(resource):

    # ---- 1. Ensure code.text ----
    code = resource.get("code", {})
    if isinstance(code, dict):
        if not code.get("text"):
            coding = code.get("coding", [])
            if coding and isinstance(coding, list):
                display = coding[0].get("display") or coding[0].get("code")
                if display:
                    resource.setdefault("code", {})["text"] = display

    # ---- 2. Normalize performed fields ----
    performed_period = resource.get("performedPeriod")
    performed_datetime = resource.get("performedDateTime")

    # If performedPeriod already exists and has start → keep it
    if isinstance(performed_period, dict) and performed_period.get("start"):
        start_date = performed_period.get("start")

    # Else if performedDateTime exists → convert to performedPeriod
    elif performed_datetime:
        start_date = performed_datetime
        resource["performedPeriod"] = {"start": performed_datetime}

    # Else fallback to meta.lastUpdated (very defensive)
    else:
        meta = resource.get("meta", {})
        start_date = meta.get("lastUpdated")

        if start_date:
            resource["performedPeriod"] = {"start": start_date}

    # ---- 3. Ensure sort_date ----
    if start_date:
        resource["sort_date"] = start_date[:10]

    return resource

def normalize_immunization_for_cms(resource):

    # ---- 1. Ensure vaccineCode.text ----
    vaccine = resource.get("vaccineCode", {})
    if isinstance(vaccine, dict):
        if not vaccine.get("text"):
            coding = vaccine.get("coding", [])
            if coding and isinstance(coding, list):
                display = coding[0].get("display") or coding[0].get("code")
                if display:
                    resource.setdefault("vaccineCode", {})["text"] = display

    # ---- 2. Normalize occurrence fields ----
    date_value = None

    # Case 1: occurrenceDateTime (most common)
    if resource.get("occurrenceDateTime"):
        date_value = resource["occurrenceDateTime"]

    # Case 2: occurrencePeriod.start
    elif isinstance(resource.get("occurrencePeriod"), dict):
        period = resource["occurrencePeriod"]
        if period.get("start"):
            date_value = period["start"]

    # Case 3: occurrenceString
    elif resource.get("occurrenceString"):
        date_value = resource["occurrenceString"]

    # Case 4: recorded (fallback)
    elif resource.get("recorded"):
        date_value = resource["recorded"]

    # Case 5: meta.lastUpdated (last defensive fallback)
    elif isinstance(resource.get("meta"), dict):
        date_value = resource["meta"].get("lastUpdated")

    if date_value:
        resource["date"] = date_value
        resource["sort_date"] = date_value[:10]

    return resource


def normalize_condition_for_cms(resource):

    # ---- 1. Ensure code.text ----
    code = resource.get("code", {})
    if isinstance(code, dict):
        if "text" not in code:
            coding = code.get("coding", [])
            if coding:
                display = coding[0].get("display") or coding[0].get("code")
                if display:
                    resource["code"]["text"] = display

    # ---- 2. Ensure clinicalStatus.coding[0].code ----
    clinical = resource.get("clinicalStatus")

    if clinical:
        if isinstance(clinical, dict):
            if "coding" not in clinical and "text" in clinical:
                resource["clinicalStatus"] = {
                    "coding": [
                        {"code": clinical["text"].lower()}
                    ]
                }
        elif isinstance(clinical, str):
            resource["clinicalStatus"] = {
                "coding": [
                    {"code": clinical.lower()}
                ]
            }
    else:
        # optional: if missing completely
        resource["clinicalStatus"] = {
            "coding": [
                {"code": "unknown"}
            ]
        }

    # ---- 3. Ensure onsetDateTime ----
    if "onsetDateTime" not in resource:
        onset_period = resource.get("onsetPeriod", {})
        if isinstance(onset_period, dict) and "start" in onset_period:
            resource["onsetDateTime"] = onset_period["start"]

    return resource


def _split_csv_ids(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(p).strip() for p in value if str(p).strip()]
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", errors="replace")
    s = str(value).strip()
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def _row_field_ci(row, name):
    if not isinstance(row, dict):
        return None
    nl = name.lower()
    for k, v in row.items():
        if isinstance(k, str) and k.lower() == nl:
            return v
    return None


def _row_has_image_id(row):
    return isinstance(row, dict) and _row_field_ci(row, "image_id") is not None


_medication_s3_session = None
_medication_s3_session_sig = None
_medication_s3_clients = {}
_bucket_region_cache = {}


def _medication_s3_boto_credentials():
    """
    Match credentials used elsewhere in this app (main.py sets access_key / secret_key;
    some paths use AWS_ACCESS_KEY / AWS_SECRET_KEY; boto3 standard is *_ID / *_ACCESS_KEY).
    If none are set, boto3 uses the default chain (instance role, ~/.aws, etc.).
    """
    ak = (
        os.getenv("AWS_ACCESS_KEY_ID")
        or os.getenv("AWS_ACCESS_KEY")
        or os.environ.get("access_key")
    )
    sk = (
        os.getenv("AWS_SECRET_ACCESS_KEY")
        or os.getenv("AWS_SECRET_KEY")
        or os.environ.get("secret_key")
    )
    return ak, sk


def _medication_s3_session():
    global _medication_s3_session, _medication_s3_session_sig
    ak, sk = _medication_s3_boto_credentials()
    st = os.getenv("AWS_SESSION_TOKEN") or None
    sig = (ak or "", sk or "", st or "")
    if _medication_s3_session is not None and _medication_s3_session_sig == sig:
        return _medication_s3_session
    if ak and sk:
        _medication_s3_session = boto3.Session(
            aws_access_key_id=ak,
            aws_secret_access_key=sk,
            aws_session_token=st,
        )
    else:
        _medication_s3_session = boto3.Session()
    _medication_s3_session_sig = sig
    return _medication_s3_session


def _normalize_bucket_location_constraint(loc):
    if loc is None:
        return "us-east-1"
    if loc == "EU":
        return "eu-west-1"
    return loc


def _discover_bucket_region(session, bucket: str) -> str:
    if bucket in _bucket_region_cache:
        return _bucket_region_cache[bucket]
    try:
        probe = session.client(
            "s3",
            region_name="us-east-1",
            config=Config(signature_version="s3v4"),
        )
        loc = probe.get_bucket_location(Bucket=bucket).get("LocationConstraint")
        reg = _normalize_bucket_location_constraint(loc)
    except Exception as e:
        print(f"medication attachment S3 get_bucket_location failed for {bucket!r}: {e}")
        reg = "us-east-1"
    _bucket_region_cache[bucket] = reg
    return reg


def _region_for_medication_s3(session, bucket: str) -> str:
    return (
        os.getenv("HEKMA_FILE_UPLOAD_REGION")
        or os.getenv("AWS_REGION")
        or os.getenv("AWS_DEFAULT_REGION")
        or _discover_bucket_region(session, bucket)
    )


def _medication_attachment_s3_client(bucket: str):
    """
    S3 client for presigned GETs: SigV4, correct region (explicit env or bucket location).
    """
    session = _medication_s3_session()
    region = _region_for_medication_s3(session, bucket)
    cache_key = (bucket, region, _medication_s3_session_sig)
    if cache_key in _medication_s3_clients:
        return _medication_s3_clients[cache_key]
    cfg = Config(signature_version="s3v4")
    cli = session.client("s3", region_name=region, config=cfg)
    _medication_s3_clients[cache_key] = cli
    return cli


def _medication_attachment_s3_bucket():
    return (
        os.getenv("MEDICATION_ATTACHMENT_S3_BUCKET")
        or os.getenv("APP_AWS_SERVICES_BUCKET_NAME")
        or "hekma-file-upload-dev"
    ).strip()


def _medication_attachment_presign_expires():
    try:
        return int(os.getenv("MEDICATION_ATTACHMENT_PRESIGNED_EXPIRES_SEC", "3600"))
    except ValueError:
        return 3600


def _presign_medication_s3_object(s3_client, bucket, object_key):
    return s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": object_key},
        ExpiresIn=_medication_attachment_presign_expires(),
    )


def enrich_medication_order_attachment_urls(rows, patient_id=None, hekma_mail=None):
    """
    Populate image_url (comma-separated, parallel to image_id / image_name) for CTMS medication rows.

    Objects are expected at s3://{bucket}/{attachment_uuid}/{filename} (e.g. hekma-file-upload-dev).

    Env:
      MEDICATION_ATTACHMENT_S3_BUCKET or APP_AWS_SERVICES_BUCKET_NAME (default hekma-file-upload-dev)
      Credentials: AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY, or AWS_ACCESS_KEY + AWS_SECRET_KEY,
      or access_key + secret_key (see main.py). Else default boto3 credential chain.
      HEKMA_FILE_UPLOAD_REGION or AWS_REGION or AWS_DEFAULT_REGION; if unset, bucket region is discovered via get_bucket_location.
      MEDICATION_ATTACHMENT_PRESIGNED_EXPIRES_SEC (default 3600)
      MEDICATION_ATTACHMENT_VERBOSE_ERRORS=true adds image_url_presign_error when presign fails.
    """
    _ = patient_id, hekma_mail  # call sites pass context; URLs use S3 key id + filename only
    if not rows:
        return

    def _clear_image_url_on_medication_rows():
        for r in rows:
            if _row_has_image_id(r):
                r["image_url"] = None
                r.pop("image_url_presign_error", None)

    bucket = _medication_attachment_s3_bucket()
    if not bucket:
        _clear_image_url_on_medication_rows()
        return

    try:
        s3 = _medication_attachment_s3_client(bucket)
    except Exception:
        traceback.print_exc()
        _clear_image_url_on_medication_rows()
        return

    verbose = os.getenv("MEDICATION_ATTACHMENT_VERBOSE_ERRORS", "").lower() in (
        "1",
        "y",
        "yes",
        "true",
    )

    for row in rows:
        if not _row_has_image_id(row):
            continue
        ids = _split_csv_ids(_row_field_ci(row, "image_id"))
        names = _split_csv_ids(_row_field_ci(row, "image_name"))
        if not ids:
            row["image_url"] = None
            continue
        urls = []
        last_err = None
        for i, fid in enumerate(ids):
            fname = names[i] if i < len(names) else ""
            fname = str(fname).strip() if fname is not None else ""
            fid = str(fid).strip() if fid is not None else ""
            if not fid or not fname:
                continue
            object_key = f"{fid}/{fname}"
            try:
                urls.append(_presign_medication_s3_object(s3, bucket, object_key))
            except Exception as ex:
                last_err = str(ex)
                traceback.print_exc()
        row["image_url"] = ",".join(urls) if urls else None
        if verbose and not urls and ids:
            if last_err:
                row["image_url_presign_error"] = last_err[:300]
            elif not names:
                row["image_url_presign_error"] = "image_name_empty_or_missing"
            elif all(
                not (i < len(names) and str(names[i]).strip())
                for i in range(len(ids))
            ):
                row["image_url_presign_error"] = "image_name_segments_empty_for_each_image_id"


def get_data(sql, params, event_type: str = None, mobile_flag=None):
    
  with pg_transaction(dict_cursor=True) as (conn, cursor):

    cursor.execute(sql, params)
    rows = cursor.fetchall()
    total = rows[0]["total_count"] if rows else 0
    data = {
        "data": [],
        "total": total,
        "size": len(rows)
    }

    for row in rows:
        source = row["raw_resource"]

        if event_type == "Immunization":
            if "occurrenceDateTime" in source:
                source["date"] = source["occurrenceDateTime"]

        elif event_type == "Observation":
            if "category" in source and isinstance(source["category"], list):
                source["category"] = source["category"][0] if source["category"] else {}

        event_info = es_index_map.get(event_type)

        if mobile_flag and event_info and 'mobile_source' in event_info:
            source = {k: source.get(k) for k in event_info['mobile_source']}
          

        data["data"].append(source)


    return data


# def get_count(index, body):
#     es = ElasticSearchConnection()
#     response = es.count(index=index, body=body)
#     return response['count']


def get_count(table, patient_id=None, hekma_mail=None, active_column=None, active_value=None):
    """
    Used only for activeCount logic.
    """
    ALLOWED_TABLES = {
        "condition",
        "allergy",
        "medication_order",
        "immunization",
        "observation",
        "procedure"
    }

    if table not in ALLOWED_TABLES:
        raise ValueError(f"Invalid table: {table}")

    with pg_transaction(dict_cursor=False) as (conn, cursor):

        where_clauses = []
        params = {}

        if not append_id_only_scope(
            where_clauses, params, pid_column="patient_id", patient_id=patient_id
        ):
            return 0

        # Active condition (AND)
        if active_column and active_value is not None:
            where_clauses.append(f"{active_column} = %(active_value)s")
            params["active_value"] = active_value

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

        sql = f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE {where_sql}
        """

        cursor.execute(sql, params)
        count = cursor.fetchone()[0]


        return count



# def get_es_query(event_type, hekma_mail=None, patient_id=None, start=None, size=None, mobile_flag=None):

#     if event_type in es_index_map.keys():
#         event_info = es_index_map.get(event_type)
#         body = {
#             "query": {
#                 "match": {
#                 }
#             },
#             "sort": {
#                 event_info.get('sort_field'): {"order": "desc"}
#             },
#             "from": start, "size": size
#         }
#         if patient_id and hekma_mail:
#             should = list()
#             should.append({
#                 "match": {
#                     event_info.get('patient_field'): "Patient/" + patient_id
#                 }
#             }
#             )
#             should.append({
#                 "match": {
#                     "hekma_mail.keyword": hekma_mail
#                 }
#             }
#             )
#             body['query'] = {
#                 "bool": {
#                     "should": should
#                 }
#             }
#         elif hekma_mail:
#             body['query']['match']['hekma_mail.keyword'] = hekma_mail
#         else:
#             #print(body['query']['match'])
#             #print(event_info.get('patient_field'))
#             #print("Patient/" + patient_id)
#             body['query']['match'][event_info.get('patient_field')] = "Patient/" + patient_id
#         if '_source' in event_info:
#             body['_source'] = event_info.get('_source')
#         if mobile_flag and 'mobile_source' in event_info:
#             body['_source'] = event_info.get('mobile_source')

#         print(body)
#         return event_info.get('index'), body
#     else:
#         return None, None


def get_es_query(event_type, hekma_mail=None, patient_id=None, start=None, size=None, mobile_flag=None):
    """
    Returns: table_name, (sql, params)
    """

    if event_type not in es_index_map:
        return None, None

    event_info = es_index_map[event_type]
    table = event_info.get("index")

    where_clauses = []
    params = {}

    pid_column = "id" if table == "patient" else "patient_id"

    if not append_id_only_scope(
        where_clauses, params, pid_column=pid_column, patient_id=patient_id
    ):
        return None, None

    if table.startswith("fastenhealth_"):
        where_clauses.append(EHR_SOURCE_PREDICATE)

    # WHERE clause
    where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"

    # # Sorting
    # # Map ES sort_field → PG column
    # sort_field_map = {
    #     "Condition": "onset_date",
    #     "Condition_CMS": "onset_date",

    #     "AllergyIntolerance": "onset_date",
    #     "AllergyIntolerance_CMS": "onset_date",

    #     "MedicationOrder": "date_written",
    #     "MedicationOrder_CMS": "date_written",

    #     "Immunization": "immunization_date",
    #     "Immunization_CMS": "immunization_date",

    #     "Observation": "observation_date",
    #     "Observation_CMS": "observation_date",
    # }

    # sort_column = sort_field_map.get(event_type)

    # if not sort_column:
    #     # Fallback safety (should not happen for patientdetail resources)
    #     sort_column = "created_at"


    if table.startswith("fastenhealth_"):
        order_clause = "ORDER BY created_at DESC"
    else:
        order_clause = "ORDER BY sort_date DESC"

    # Pagination
    params["limit"] = size if size is not None else 100
    params["offset"] = start if start is not None else 0

    # Final SQL
    sql = f"""
        SELECT raw_resource, COUNT(*) OVER() AS total_count
        FROM {table}
        WHERE {where_sql}
        {order_clause}
        LIMIT %(limit)s OFFSET %(offset)s

    """

    return table, (sql, params)


def get_combinedResult(email, patient_id, type, from_index, total_size, src, vital:str=None, lab:str=None):
    mapping_json = get_mapping_json()

    patient_id = resolve_chart_patient_id(patient_id, email)
    email = None
    if not patient_id:
        return [], "N", 0, 0
    ctms_patient_ids = resolve_ctms_patient_ids(patient_id, None)

    # Existing allergy-like diagnoses → Allergies so classic EHR Allergies UI sees them.
    if type == "AllergyIntolerance" and ctms_patient_ids:
        try:
            from ...services.clinical_scans.allergy_promotion import (
                sync_allergy_like_conditions_to_allergies,
            )
            for pid in ctms_patient_ids:
                sync_allergy_like_conditions_to_allergies(str(pid))
        except Exception:
            pass

    final_result = []
    if type in mapping_json:
        for sub_type in mapping_json[type]:
            try:
                if sub_type == "HekmaBmi":
                    bmi_patient_ids = list(ctms_patient_ids or [])
                    if patient_id:
                        bmi_patient_ids.append(patient_id)
                    final_result = final_result + fetch_bmi_dashboard_rows(bmi_patient_ids)
                    continue
                if 'type' in mapping_json['mapping'][sub_type]:
                    cur_obj = mapping_json['mapping'][sub_type]
                    if cur_obj['type']=="ctms":
                        if sub_type == "InternalMedication":
                            if not ctms_patient_ids:
                                continue
                            sql = build_ctms_sql(cur_obj['sql'], ctms_patient_ids)
                            print(sql)
                            with mysql_connection() as mysql:
                                cursor = mysql.cursor(dictionary=True)
                                cursor.execute(sql)
                                rows = cursor.fetchall()
                            print(rows)
                            for r in rows:
                                if not r.get("createdBy"):
                                    r["createdBy"] = patient_id
                            final_result = final_result + rows
                            continue
                        module = INTERNAL_TO_MODULE.get(sub_type)
                        if not module:
                            continue
                        id_candidates = []
                        for raw in list(ctms_patient_ids or []):
                            s = str(raw).strip()
                            if s and s not in id_candidates:
                                id_candidates.append(s)
                        if patient_id:
                            s = str(patient_id).strip()
                            if s and s not in id_candidates:
                                id_candidates.append(s)
                        if not id_candidates:
                            continue
                        from ...services.clinical_fhir.hekma_clinical_store import (
                            HekmaClinicalStore,
                        )
                        store = HekmaClinicalStore()
                        seen_ids = set()
                        for pid in id_candidates:
                            try:
                                rows = store.list_for_patient(pid, module, limit=500)
                            except Exception as exc:
                                print(f"Issue listing {sub_type} for {pid}: {exc}")
                                continue
                            for rec in rows:
                                rid = rec.get("id")
                                if rid in seen_ids:
                                    continue
                                seen_ids.add(rid)
                                final_result.append(
                                    to_internal_dashboard_row(sub_type, rec, pid)
                                )
                        continue
                index, body = get_es_query(event_type=sub_type, patient_id=patient_id, hekma_mail=email,
                                           size=10000, start=0, mobile_flag=None)
                if body:
                    sql, params = body
                    result = get_data(sql, params, event_type=type)
                    if result["size"] > 0:
                        for element in result["data"]:
                            if sub_type == "fastenhealth_condition":
                               element = normalize_condition_for_cms(element)
                            if sub_type == "fastenhealth_immunization":
                                 element = normalize_immunization_for_cms(element)
                            if sub_type == "fastenhealth_procedure":
                                 element = normalize_procedure_for_cms(element)
                            if sub_type == "fastenhealth_allergyintolerance":
                                 element = normalize_allergy_for_cms(element)
                            if sub_type == "fastenhealth_observation":
                                 element = normalize_observation_for_cms(element)
                            if sub_type == "fastenhealth_medicationorder":
                                element = normalize_medication_for_cms(element)
     


     
   

                            try:
                                final_element = {}
                                if src == "Y":
                                    final_element["src"] = element
                                for key in mapping_json['mapping'][sub_type]:
                                    flag = 1
                                    transform = mapping_json['mapping'][sub_type][key].split(".")
                                    nested = None
                                    rec = copy.deepcopy(element)
                                    for sub in transform:
                                        special = sub.split("|")
                                        sub = special[0]
                                        res = sub.split("_")
                                        sub = res[0]
                                        sub_result = sub.split("[")
                                        sub = sub_result[0]
                                        if "Name" in final_element and "Blood" in final_element["Name"] and isinstance(rec, list) and len(rec)>1:
                                            rec_all = list()
                                            rec_before = rec
                                            for rec in rec_before:
                                                if len(sub_result) > 1:
                                                    if sub in rec:
                                                        if isinstance(rec[sub], list):
                                                            if "Name" in final_element and "Blood" in final_element[
                                                                "Name"] and len(rec[sub])>1:
                                                                rec = rec[sub]
                                                            else:
                                                                rec = rec[sub][0]
                                                        else:
                                                            rec = rec[sub]
                                                    else:
                                                        flag = 0
                                                        break
                                                else:
                                                    if len(special) > 1 and special[1] == "O":
                                                        if sub in rec:
                                                            rec = rec[sub]
                                                        else:
                                                            flag = 0
                                                            break
                                                    else:
                                                        if sub in rec:
                                                            rec = rec[sub]
                                                        else:
                                                            flag = 0
                                                            break
                                                rec_all.append(rec)
                                            rec = rec_all
                                        else:
                                            if len(sub_result) > 1:
                                                if sub in rec:
                                                    if isinstance(rec[sub], list):
                                                        if "Name" in final_element and "Blood" in final_element["Name"] and len(rec[sub])>1:
                                                            rec = rec[sub]
                                                        else:
                                                            rec = rec[sub][0]

                                                    else:
                                                        rec = rec[sub]
                                                else:
                                                    flag = 0
                                                    break
                                            else:
                                                if len(special) > 1 and special[1] == "O":
                                                    if sub in rec:
                                                        rec = rec[sub]
                                                    else:
                                                        flag = 0
                                                        break
                                                else:
                                                    if sub in rec:
                                                        rec = rec[sub]
                                                    else:
                                                        flag = 0
                                                        break
                                    if len(res) > 1 and flag == 1:
                                        if len(special) > 1 and special[1] == "O":
                                            if isinstance(rec, (list, str)):
                                                rec = rec[:int(res[1])]
                                        else:
                                            rec = rec[:int(res[1])]
                                    if flag == 1:
                                        if "optional" in key:
                                            key = "_".join(key.split("_")[1:])
                                        if type == "Observation" and key == "value_quantity" and not isinstance(rec, list):
                                            final_element[key] = [rec]
                                        else:
                                            final_element[key] = rec
                                if sub_type == "fastenhealth_observation":
                                    for extra in ("loincCode", "fieldKey", "catalogCategory"):
                                        if element.get(extra):
                                            final_element[extra] = element.get(extra)
                                final_result.append(final_element)

                            except Exception as e:
                                print(e)
                                print("Issue")
                                print(element)
            except Exception as e:
                print("Issue with sub_type:"+ sub_type)
                print(e)
    observation_flag = "N"
    vital_count = 0
    lab_count = 0
    if type == "Observation":
        if vital:
            if vital=='Y':
                final_result = [item for item in final_result if item.get('category_code') == "vital-signs"]
            else:
                final_result = [item for item in final_result if item.get('category_code', 'dummy') != "vital-signs"]

        elif lab:
            if lab=='Y':
                final_result = [item for item in final_result if item.get('category_code') == "laboratory"]
            else:
                final_result = [item for item in final_result if item.get('category_code', 'dummy') != "laboratory"]
        else:
            observation_flag = "Y"
            vital_count = 0
            lab_count = 0
            for item in final_result:
                if item.get('category_code') == "vital-signs":
                    vital_count = vital_count + 1
                elif item.get('category_code') == "laboratory":
                    lab_count = lab_count + 1

    final_result = sorted(final_result, key=lambda x: str(x.get('sort_date', '1970-01-01')), reverse=True)
    enrich_medication_order_attachment_urls(final_result, patient_id=patient_id, hekma_mail=email)
    print("result")
    print(final_result)
    return final_result, observation_flag, vital_count, lab_count
    #paginated_data = final_result[from_index:from_index + total_size]
    #response = {
    #    "data": paginated_data,
    #    "total": len(final_result),
    #    "from": from_index,
    #    "size": total_size,
    #    "combined_result": mapping_json[type]
    #}
    #if observation_flag == "Y":
    #    response['vital_count'] = vital_count
    #    response['lab_count'] = lab_count
    #return response


def resource_type_handler(event, context):
    try:
        print(event)
        event = event['params']['querystring']
        src = None
        if 'src' in event:
            src = event['src']
        start = 0
        if 'from' in event:
            start = int(event['from'])
        size = 100
        if 'size' in event:
            size = int(event['size'])
        mobile_flag = None
        if 'mobile' in event:
            mobile_flag = event['mobile']
        data = {}
        patientId = None
        hekma_mail = None
        if 'hekmaMail' in event:
            hekma_mail = normalize_identifier(event['hekmaMail'])
        if 'patientId' in event:
            patientId = normalize_identifier(event['patientId'])
        jwt_user_id = None
        if "jwtUserId" in event:
            jwt_user_id = normalize_identifier(event["jwtUserId"])
        patientId = resolve_chart_patient_id(patientId, hekma_mail, jwt_user_id)
        hekma_mail = None
        combinedFlag = "N"
        if 'combinedFlag' in event:
            combinedFlag = event['combinedFlag']
        vital = None
        if "vital" in event:
            vital = event['vital']
        lab = None
        if "lab" in event:
            lab = event['lab']
        if combinedFlag == "Y":
            if event['eventType'] in ["Condition", "Procedure", "Immunization", "Observation", "AllergyIntolerance", "MedicationOrder"]:
                # redis key
                redis_key = "details_" + event['eventType']
                if patientId:
                    redis_key = redis_key + "_" + patientId
                else:
                    redis_key = redis_key + "_"
                redis_key = redis_key + "_"
                if combinedFlag:
                    redis_key = redis_key + "_" + combinedFlag
                else:
                    redis_key = redis_key + "_"
                if vital:
                    redis_key = redis_key + "_" + vital
                else:
                    redis_key = redis_key + "_"
                if lab:
                    redis_key = redis_key + "_" + lab
                else:
                    redis_key = redis_key + "_"
                try:
                    redis_exist, redis_result = get_key(redis_key)
                except Exception as e:
                    print("Redis not exist" + str(e))
                    redis_exist = None
                final_result = None
                if redis_exist and redis_exist == 1 and os.getenv("DISABLE_REDIS") != "Y":
                    print("Redis data exist!!")
                    final_result = json.loads(redis_result)
                    if event['eventType'] == "MedicationOrder":
                        enrich_medication_order_attachment_urls(final_result, patient_id=patientId, hekma_mail=hekma_mail)
                else:
                    final_result, observation_flag, vital_count, lab_count = get_combinedResult(hekma_mail, patientId, event['eventType'], start, size, src, vital=vital, lab=lab)
                    set_key(redis_key, json.dumps(final_result, default=str))
                paginated_data = final_result[start:start + size]
                mapping_json = get_mapping_json()

                response = {
                    "data": paginated_data,
                    "total": len(final_result),
                    "from": start,
                    "size": size,
                    "combined_result": mapping_json[event['eventType']]
                }
                if event['eventType']=="Observation":
                    lab_references = get_lab_references()
                    response["lab_references"] = lab_references["lab_references"]

                return response

        table, query = get_es_query(
            event['eventType'],
            patient_id=patientId,
            hekma_mail=hekma_mail,
            start=start,
            size=size,
            mobile_flag=mobile_flag
        )

        if query:
            sql, params = query

            data = get_data(
                sql,
                params,
                event_type=event['eventType'],
                mobile_flag=mobile_flag
            )
            data['from'] = start

            event_info = es_index_map.get(event['eventType'])

            # Active count (PostgreSQL)

            COLUMN_MAP = {
            "clinicalStatus": "clinical_status",   # Condition
            "status": "status"                     # Allergy, Medication
            }

            active_info = event_info.get("active")
            if active_info:
                active_field = list(active_info.keys())[0]
                active_value = active_info[active_field]

                active_column = COLUMN_MAP.get(active_field)
                if not active_column:
                     raise ValueError(f"Unsupported active field: {active_field}")

                count = get_count(
                    table=table,               
                    patient_id=patientId,
                    hekma_mail=hekma_mail,
                    active_column=active_column,
                    active_value=active_value
                )

                data["activeCount"] = count

        return data
    except Exception as e:
        print(e)
        traceback.print_exc()
        return {}


if __name__ == '__main__':
    mapping_json = get_mapping_json()

    final_result = []
    #email = "balaanbalagan05@gmail.com"
    email = "Hekmalogin03@gmail.com"
    #email = "m.aria1he.rnand.ez456@gmail.com"
    email=None
    patient_id="0e109e66-4f48-9720-1eb8-5179b11227a2"
    #patient_id=None
    type = "Condition"
    src="N"
    i=0

    if type in mapping_json:
        for sub_type in mapping_json[type]:
            try:
                if patient_id and 'type' in mapping_json['mapping'][sub_type]:
                    cur_obj = mapping_json['mapping'][sub_type]
                    if cur_obj['type']=="ctms":
                        sql=str(cur_obj['sql']).format(patient_id)
                        print(sql)
                        with mysql_connection() as mysql:
                            cursor = mysql.cursor(dictionary=True)
                            cursor.execute(sql)
                            rows = cursor.fetchall()
                        for r in rows:
                            if not r.get("createdBy"):
                                r["createdBy"] = patient_id
                        final_result = final_result + rows
                        continue
                index, body=get_es_query(event_type=sub_type, patient_id=patient_id, hekma_mail=email,
                             size=2000, start=0, mobile_flag=None)
                if body:
                    result = get_data(index=index, body=body, event_type=type)
                    print(result["size"])
                    #print(result)
                    if result["size"]>0:
                        for element in result["data"]:
                            print_flag = "N"
                            #print(element)
                            #print(element.keys())
                            #if 'component' in element and len(element['component'])>1:
                            #    print( len(element['component']))
                            #    print(element)
                            #    print_flag = "Y"
                            if print_flag == "Y":
                                print("Element\n\n\n")
                                print(element)
                            final_element = {}
                            if src == "Y":
                                final_element["src"] = element
                            for key in mapping_json['mapping'][sub_type]:
                                #if "category_code" not in key:
                                #    continue
                                print(key)
                                if key == "result_text":
                                    print_flag = "Y"
                                else:
                                    print_flag = "N"
                                if print_flag == "Y":

                                    print(key)
                                    print(mapping_json['mapping'][sub_type][key])
                                flag = 1
                                transform = mapping_json['mapping'][sub_type][key].split(".")
                                nested = None
                                rec = copy.deepcopy(element)
                                for sub in transform:
                                    if print_flag == "Y":
                                        print(sub)
                                        print(rec)
                                        print(final_element)
                                    special = sub.split("|")
                                    sub = special[0]
                                    res = sub.split("_")
                                    sub = res[0]
                                    sub_result = sub.split("[")
                                    sub = sub_result[0]
                                    if "Name" in final_element and "Blood" in final_element["Name"] and isinstance(rec, list) and len(rec) > 1:
                                        print("Dinky")
                                        rec_all = list()
                                        rec_before = rec
                                        for rec in rec_before:
                                            if len(sub_result) > 1:
                                                if sub in rec:
                                                    if isinstance(rec[sub], list):
                                                        if "Name" in final_element and "Blood" in final_element["Name"] and len(rec[sub])>1:
                                                            rec = rec[sub]
                                                        else:
                                                            rec = rec[sub][0]
                                                    else:
                                                        rec = rec[sub]
                                                else:
                                                    flag = 0
                                                    break
                                            else:
                                                if len(special) > 1 and special[1] == "O":
                                                    if sub in rec:
                                                        rec = rec[sub]
                                                    else:
                                                        flag = 0
                                                        break
                                                else:
                                                    if sub in rec:
                                                        rec = rec[sub]
                                                    else:
                                                        flag = 0
                                                        break
                                            rec_all.append(rec)
                                        rec = rec_all
                                    else:
                                        print("Banky")

                                        if len(sub_result) > 1:
                                            if sub in rec:
                                                if isinstance(rec[sub], list):
                                                    if "Name" in final_element and "Blood" in final_element["Name"] and len(rec[sub])>1:
                                                        rec = rec[sub]
                                                    else:
                                                        rec = rec[sub][0]
                                                else:
                                                    rec = rec[sub]
                                            else:
                                                flag = 0
                                                break
                                        else:
                                            if len(special) > 1 and special[1] == "O":
                                                if sub in rec:
                                                    rec = rec[sub]
                                                else:
                                                    flag = 0
                                                    break
                                            else:
                                                if sub in rec:
                                                    rec = rec[sub]
                                                else:
                                                    flag = 0
                                                    break
                                if len(res) > 1 and flag == 1:
                                    if len(special) > 1 and special[1] == "O":
                                        if isinstance(rec, (list, str)):
                                            rec = rec[:int(res[1])]
                                    else:
                                        rec = rec[:int(res[1])]
                                if flag == 1:
                                    if "optional" in key:
                                        key="_".join(key.split("_")[1:])
                                    if type == "Observation" and key == "value_quantity" and not isinstance(rec, list):
                                        final_element[key] = [rec]
                                    else:
                                        final_element[key] = rec
                            final_result.append(final_element)
            except Exception as e:
                print("Issue with sub_type:"+ sub_type)
                print(e)
                raise


    print(sorted(final_result, key=lambda x: str(x.get('sort_date', '1970-01-01')), reverse=True))
    #sorted(final_result,)
    #print(len(final_result))
    #print(data)

    #print(get_es_query(event_type="Immunization", patient_id="856c851d-f8e9-8868-f5e0-b61403f99394", hekma_mail=None, size=100, start=0, mobile_flag='N'))