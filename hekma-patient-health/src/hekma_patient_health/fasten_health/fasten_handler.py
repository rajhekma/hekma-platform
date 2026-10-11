import os
import json
import requests
import boto3
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

logger = logging.getLogger("fasten_ehr")
from datetime import datetime
from psycopg2.extras import Json
from ..awsutils.postgresql_utils import pg_transaction
from .patient_resolver import resolve_patient_id, resolve_hekma_details
from .ingest_export import ingest_fasten_export
from .ehr_summary_cache_repo import invalidate_cached_summary
from .trial_gpt_ehr_client import notify_trial_gpt_ehr_ingest
from ..cache_service.reprocess_cache import reprocess_paritent_id

logger.setLevel(logging.INFO)

FASTEN_PUBLIC_ID = os.getenv("FASTEN_PUBLIC_ID")
FASTEN_PRIVATE_KEY = os.getenv("FASTEN_PRIVATE_KEY")
BASE_URL = os.getenv("FASTEN_BASE_URL")

TEFCA_CCDA_FIXTURES = frozenset({"myra-jones.xml", "lennie-connell.xml"})

class FastenApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None, response_body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body or {}


def _sanitize_fasten_credential(value: str | None) -> str | None:
    """
    Normalize credentials loaded from env files or secret stores.
    A trailing backslash is a common copy/paste artifact and breaks Basic auth.
    """
    if not value:
        return value
    cleaned = value.strip().strip('"').strip("'")
    while cleaned.endswith("\\"):
        cleaned = cleaned[:-1]
    return cleaned


def _parse_fasten_error_response(resp: requests.Response) -> str:
    try:
        payload = resp.json()
    except ValueError:
        return resp.text or f"HTTP {resp.status_code}"

    if isinstance(payload, dict):
        for key in ("error", "message", "detail"):
            if payload.get(key):
                return str(payload[key])
    return resp.text or f"HTTP {resp.status_code}"


def _raise_for_fasten_response(resp: requests.Response):
    if resp.ok:
        return
    message = _parse_fasten_error_response(resp)
    body = None
    try:
        body = resp.json()
    except ValueError:
        pass
    raise FastenApiError(message, status_code=resp.status_code, response_body=body)


EXPORT_FAILURE_MESSAGES = {
    "tefca_no_documents_found": (
        "No medical records were found for this patient in the TEFCA network. "
        "This is common in test mode; configure FASTEN_TEFCA_FIXTURE or pass fixtures.tefca_ccda."
    ),
    "token_refresh_failure": "The health record connection expired. Please reconnect.",
    "scope_patient_missing": (
        "Required patient read permissions were not granted during consent."
    ),
    "resource_patient_failure": "Failed to retrieve patient demographics from the health system.",
    "resource_invalid_content": "A critical health record could not be parsed.",
    "suppressed_please_contact": (
        "Export failed. Please contact support if the issue persists."
    ),
}


def get_auth_tuple():
    public_id = _sanitize_fasten_credential(FASTEN_PUBLIC_ID)
    private_key = _sanitize_fasten_credential(FASTEN_PRIVATE_KEY)
    if not public_id or not private_key:
        raise ValueError("Fasten credentials not configured properly")
    return (public_id, private_key)


def is_test_mode() -> bool:
    return (FASTEN_PUBLIC_ID or "").startswith("public_test_")


def _default_tefca_fixture() -> str | None:
    explicit = os.getenv("FASTEN_TEFCA_FIXTURE", "").strip()
    if explicit:
        return explicit
    auto = os.getenv("FASTEN_AUTO_TEFCA_FIXTURE", "true").lower()
    if auto in ("1", "true", "yes") and is_test_mode():
        return "myra-jones.xml"
    return None


def _build_export_body(org_connection_id: str, tefca_ccda_fixture: str | None = None) -> dict:
    body = {"org_connection_id": org_connection_id}
    fixture = tefca_ccda_fixture or _default_tefca_fixture()
    if fixture:
        if fixture not in TEFCA_CCDA_FIXTURES:
            raise ValueError(
                f"Invalid tefca_ccda fixture '{fixture}'. "
                f"Allowed: {', '.join(sorted(TEFCA_CCDA_FIXTURES))}"
            )
        if not is_test_mode():
            raise ValueError("fixtures.tefca_ccda is only available in Fasten test mode")
        body["fixtures"] = {"tefca_ccda": fixture}
    return body


def write_s3_direct(bucket_name, file_path, content):
    logger.info("Writing raw data to S3 | bucket=%s | path=%s", bucket_name, file_path)

    s3 = boto3.resource(
        "s3",
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-west-1"),
    )
    s3.Object(bucket_name, file_path).put(Body=content)


def request_patient_export(org_connection_id: str, tefca_ccda_fixture: str | None = None):
    logger.info("Initiating Fasten export | org_connection_id=%s", org_connection_id)

    url = f"{BASE_URL}/bridge/fhir/ehi-export"
    body = _build_export_body(org_connection_id, tefca_ccda_fixture)
    resp = requests.post(
        url,
        auth=get_auth_tuple(),
        json=body
    )
    _raise_for_fasten_response(resp)

    update_connection_export_status(org_connection_id, export_status="initiated")
    logger.info("Export initiated successfully | response=%s", resp.json())
    return resp.json()


def revoke_vault_connections(email: str):
    if not is_test_mode():
        raise ValueError("Vault revoke is only available in Fasten test mode")

    url = f"{BASE_URL}/bridge/vault_connection/revoke"
    resp = requests.post(
        url,
        auth=get_auth_tuple(),
        json={"email": email},
    )
    _raise_for_fasten_response(resp)
    logger.info("Vault connections revoked | email=%s", email)
    return resp.json()


def process_webhook_data(data: dict, patient_id: str = None):
    event_type = data.get("type") or data.get("event_type")

    logger.info(
        "Fasten webhook received | event_type=%s | top_level_keys=%s",
        event_type,
        list(data.keys())
    )

    if event_type == "patient.ehi_export_success":
        return process_export_success(data, patient_id)
    if event_type == "patient.ehi_export_failed":
        return process_export_failed(data, patient_id)
    if event_type == "patient.connection_success":
        return process_connection_success(data, patient_id)
    if event_type == "webhook.test":
        return {"status": "ok", "type": event_type}
    if event_type == "widget.complete":
        return process_widget_complete(data, patient_id)
    if "download_links" not in str(data):
        logger.info("Fallback raw data handler triggered")
        return process_raw_data(data, patient_id)

    logger.info("Webhook ignored | event_type=%s", event_type)
    return {"status": "ignored", "type": event_type}


def process_raw_data(data: dict, patient_id: str = None):
    if not patient_id:
        patient_id = data.get('patientId') or data.get('patient_id') or "unknown_patient"

    logger.info("Processing raw Fasten data | patient_id=%s", patient_id)

    bucket_name = os.environ.get('FASTEN_BUCKET_NAME', 'hekma-fasten-health-raw')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    file_path = f"{patient_id}/{timestamp}_fasten_data.json"

    write_s3_direct(bucket_name, file_path, json.dumps(data))
    return {"status": "success", "bucket": bucket_name, "path": file_path}


def process_widget_complete(data: dict, patient_id: str = None):
    logger.info("Entered widget.complete handler")

    if not patient_id:
        patient_id = (
            data.get("patientId")
            or data.get("patient_id")
            or "unknown_patient"
        )

    logger.info("Resolved patient_id for widget.complete | patient_id=%s", patient_id)

    items = data.get("data", [])
    logger.info("Widget contains %d org connections", len(items))

    results = []

    for item in items:
        org_conn_id = item.get("org_connection_id")
        tefca_directory_id = item.get("tefca_directory_id")

        insert_fasten_widget_event(
            patient_id=patient_id,
            payload={**data, "data": [item]},
            org_connection_id=org_conn_id,
            tefca_directory_id=tefca_directory_id,
        )

        if org_conn_id:
            try:
                request_patient_export(org_conn_id)
                results.append({
                    "org_connection_id": org_conn_id,
                    "tefca_directory_id": tefca_directory_id,
                    "status": "initiated",
                })
            except FastenApiError as e:
                logger.error(
                    "Fasten export rejected | org_connection_id=%s | status=%s | error=%s",
                    org_conn_id,
                    e.status_code,
                    e,
                )
                update_connection_export_status(
                    org_conn_id,
                    export_status="failed",
                    failure_reason="export_request_failed",
                )
                results.append({
                    "org_connection_id": org_conn_id,
                    "tefca_directory_id": tefca_directory_id,
                    "status": "failed",
                    "error": str(e),
                    "fasten_status_code": e.status_code,
                    "fasten_error": (e.response_body or {}).get("error"),
                })
            except Exception as e:
                logger.exception("Failed to initiate export | org_connection_id=%s", org_conn_id)
                update_connection_export_status(
                    org_conn_id,
                    export_status="failed",
                    failure_reason="export_request_failed",
                )
                results.append({
                    "org_connection_id": org_conn_id,
                    "tefca_directory_id": tefca_directory_id,
                    "status": "failed",
                    "error": str(e),
                })

    return {"status": "processed", "results": results}


def process_connection_success(data: dict, patient_id: str = None):
    payload = data.get("data", {})
    org_connection_id = payload.get("org_connection_id")
    tefca_directory_id = payload.get("tefca_directory_id")

    if not patient_id and org_connection_id:
        patient_id = resolve_patient_id(org_connection_id)

    if patient_id and org_connection_id:
        insert_fasten_widget_event(
            patient_id=patient_id,
            payload=data,
            org_connection_id=org_connection_id,
            tefca_directory_id=tefca_directory_id,
        )

    return {
        "status": "connection_recorded",
        "org_connection_id": org_connection_id,
        "tefca_directory_id": tefca_directory_id,
    }


def process_export_failed(data: dict, patient_id: str = None):
    logger.info("Entered patient.ehi_export_failed handler")

    payload = data.get("data", {})
    org_connection_id = payload.get("org_connection_id")
    failure_reason = payload.get("failure_reason", "suppressed_please_contact")

    logger.warning(
        "EHI export failed | org_connection_id=%s | failure_reason=%s",
        org_connection_id,
        failure_reason,
    )

    update_connection_export_status(
        org_connection_id,
        export_status="failed",
        failure_reason=failure_reason,
    )

    hekma_patient_id = resolve_patient_id(org_connection_id) if org_connection_id else None
    message = EXPORT_FAILURE_MESSAGES.get(
        failure_reason,
        EXPORT_FAILURE_MESSAGES["suppressed_please_contact"],
    )

    return {
        "status": "export_failed",
        "patient_id": hekma_patient_id,
        "org_connection_id": org_connection_id,
        "failure_reason": failure_reason,
        "message": message,
    }


def process_export_success(data: dict, patient_id: str = None):
    logger.info("Entered patient.ehi_export_success handler")

    payload = data.get("data", {})
    org_connection_id = payload.get("org_connection_id")

    logger.info("org_connection_id=%s", org_connection_id)

    download_links = payload.get("download_links", [])
    logger.info("Download links count=%d", len(download_links))

    hekma_patient_id = resolve_patient_id(org_connection_id)
    logger.info("Resolved hekma_patient_id=%s", hekma_patient_id)

    if not hekma_patient_id:
        logger.error("No patient mapping found | org_connection_id=%s", org_connection_id)
        raise Exception("Patient mapping not found for org_connection_id")

    hekma_details = resolve_hekma_details(hekma_patient_id)

    if not hekma_details:
        logger.error("No MySQL patient found | patient_id=%s", hekma_patient_id)
        raise Exception("MySQL patient not found")

    hekma_mail_id = hekma_details.get("email")

    logger.info(
        "Resolved patient mapping | patient_id=%s | email=%s",
        hekma_patient_id,
        hekma_mail_id,
    )

    ingested_files = 0

    for link in download_links:
        file_url = link.get("url")
        logger.info("Raw download URL=%s", file_url)

        if not file_url:
            logger.warning("Empty download URL encountered")
            continue

        file_resp = requests.get(
            file_url,
            auth=get_auth_tuple(),
            allow_redirects=True
        )
        file_resp.raise_for_status()

        logger.info(
            "Download completed | status=%s | content_length=%d",
            file_resp.status_code,
            len(file_resp.text)
        )

        try:
            logger.info(
                "Starting ingestion | patient_id=%s | resource_stats=%s",
                hekma_patient_id,
                payload.get("stats", {}).get("total_by_resource_type", {})
            )

            ingest_fasten_export(
                patient_id=hekma_patient_id,
                hekma_mail_id=hekma_mail_id,
                file_text=file_resp.text,
                total_by_resource_type=payload.get("stats", {}).get("total_by_resource_type", {}),
                org_connection_id=org_connection_id,
            )
            reprocess_paritent_id(hekma_patient_id)

            cache_invalidated = invalidate_cached_summary(hekma_patient_id)
            if cache_invalidated:
                logger.info(
                    "EHR summary cache invalidated | patient_id=%s — next summary request will regenerate",
                    hekma_patient_id,
                )
            else:
                logger.warning(
                    "EHR summary cache invalidation had no effect | patient_id=%s | "
                    "Either no cache entry existed (harmless) or a DB error occurred "
                    "(check ERROR logs above). If stale summaries are a concern, "
                    "manually call: DELETE /api/patients/%s/ehr-summary/cache",
                    hekma_patient_id, hekma_patient_id,
                )

            update_connection_export_status(org_connection_id, export_status="success")
            ingested_files += 1
            logger.info("Ingestion completed successfully")

        except Exception:
            logger.exception("Ingestion failed")
            update_connection_export_status(
                org_connection_id,
                export_status="failed",
                failure_reason="ingestion_failed",
            )
            raise

    if ingested_files > 0:
        logger.info(
            "trial_gpt_ehr notify queued after fasten export | patient_id=%s | files=%s",
            hekma_patient_id,
            ingested_files,
        )
        notify_trial_gpt_ehr_ingest(
            hekma_patient_id,
            trigger="fasten_ehi_export_success",
            force=True,
        )

    return {
        "status": "success",
        "uploaded_files": []
    }


process_fasten_data = process_webhook_data


def update_connection_export_status(
    org_connection_id: str | None,
    export_status: str,
    failure_reason: str | None = None,
):
    if not org_connection_id:
        return

    with pg_transaction(dict_cursor=False) as (_, cur):
        cur.execute(
            """
            UPDATE fasten_controller
            SET export_status = %s,
                failure_reason = COALESCE(%s, failure_reason)
            WHERE org_connection_id = %s
            """,
            (export_status, failure_reason, org_connection_id),
        )


def insert_fasten_widget_event(
    patient_id: str,
    payload: dict,
    org_connection_id: str | None = None,
    tefca_directory_id: str | None = None,
):
    logger.info(
        "Inserting widget event | patient_id=%s | org_connection_id=%s | tefca_directory_id=%s",
        patient_id,
        org_connection_id,
        tefca_directory_id,
    )

    with pg_transaction(dict_cursor=False) as (_, cur):
        cur.execute(
            """
            INSERT INTO fasten_controller
                (patient_id, data_time, fasten_health_ref, org_connection_id, tefca_directory_id, export_status)
            VALUES
                (%s, %s, %s, %s, %s, %s)
            """,
            (
                patient_id,
                datetime.utcnow(),
                Json(payload),
                org_connection_id,
                tefca_directory_id,
                "pending" if org_connection_id else None,
            )
        )


if __name__ == "__main__":
    process_fasten_data({}, "unknown_patient1")
