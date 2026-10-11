from ..awsutils.mysql_db_connection import mysql_connection
from ..redis_service import (
    batch_unlink_cache_keys,
    build_explicit_combined_detail_keys,
    del_detail_keys_for_resource,
    del_key_list,
)
from ..ehr_apis.get_headers import lambda_main as H
from ..ehr_apis.get_resource_type_detail import lambda_main as D
from ..ehr_apis.get_resource_type_detail.lambda_main import normalize_identifier
import concurrent.futures
import time


def _log_stage(stage: str, start: float, extra: str = ""):
    ms = (time.perf_counter() - start) * 1000.0
    suffix = f" {extra}" if extra else ""
    print(f"[cachereprocess] stage={stage} duration_ms={ms:.2f}{suffix}")

_bg_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

def resolve_patient(patient_id):
    # patientId is an integer column: comparing it to a non-numeric string makes MySQL
    # coerce the string (e.g. a subjectId UUID "3f4d5a23-..." becomes 3) and silently
    # match an unrelated patient. Only match patientId when the caller sent digits.
    identifier = normalize_identifier(patient_id)
    if not identifier:
        raise ValueError(f"Unusable buId for cache reprocess: {patient_id!r}")
    if identifier.isdigit():
        sql = "select patientId,subjectId,email from Patient WHERE patientId=%s"
    else:
        sql = "select patientId,subjectId,email from Patient WHERE subjectId=%s"

    with mysql_connection() as mysql:
        cursor = mysql.cursor(dictionary=True)
        cursor.execute(sql, (identifier,))
        rows = cursor.fetchall()

    if not rows:
        raise ValueError(f"No patient found for buId: {patient_id}")

    row = rows[0]
    print(row)
    return row


def get_patient_details(patient_id):
    row = resolve_patient(patient_id)
    return row['subjectId'], row['email']


def header_call(key):
    parts = key.split("_")

    patientId = parts[1] if len(parts) > 1 else None
    hekma_mail = parts[2] if len(parts) > 2 else None
    combinedFlag = parts[-1] if len(parts) > 3 else "N"
    parsed = {
        "patientId": patientId,
        "hekmaMail": hekma_mail,
        "combinedFlag": combinedFlag
    }
    event1= {}
    event1['params'] = {
        "querystring" : parsed
    }
    print(H.resource_type_handler(event1, None ))



def detail_call(key):
    try:
        parts = key.split("_", 6)

        eventType = parts[1] if len(parts) > 1 else None
        patientId = normalize_identifier(parts[2]) if len(parts) > 2 else None
        hekma_mail = normalize_identifier(parts[3]) if len(parts) > 3 else None
        combinedFlag = parts[4] if len(parts) > 4 and parts[4] != "" else "N"
        vital = parts[5] if len(parts) > 5 and parts[5] != "" else None
        lab = parts[6] if len(parts) > 6 and parts[6] != "" else None

        parsed = {
            "eventType": eventType,
            "patientId": patientId,
            "hekmaMail": hekma_mail,
            "combinedFlag": combinedFlag,
            "vital": vital,
            "lab": lab
        }

        event1 = {"params": {"querystring": parsed}}

        D.resource_type_handler(event1, None)

    except Exception as e:
        print(f"[detail_call ERROR] {e}")



def _bg_header_cleanup(subject_id, bu_id, email):
    # Perform header deletion and regeneration in background
    t0 = time.perf_counter()
    header_keys = del_key_list(["header", subject_id, bu_id, email], 2)
    _log_stage("header_redis_del_key_list", t0, f"keys_found={len(header_keys)}")
    t1 = time.perf_counter()
    for key in header_keys[:10]:   # limit
        try:
            header_call(key)
        except Exception as e:
            print(f"[header_call ERROR] {e}")

def _after_detail_futures_then_header(futures, subject_id, bu_id, email, bg_started_at=None):
    """Wait for detail cache rebuilds before header rebuild to avoid exhausting DB pools."""
    t0 = time.perf_counter()
    for fut in futures:
        try:
            fut.result()
        except Exception as e:
            print(f"detail_call failed: {e}")
    _log_stage("background_detail_warm_await", t0, f"futures={len(futures)}")
    t1 = time.perf_counter()
    _bg_header_cleanup(subject_id, bu_id, email)
    _log_stage("background_header_cleanup_total", t1)
    if bg_started_at is not None:
        _log_stage("background_pipeline_total", bg_started_at, "includes=scan+submit+await_detail+header")


def _parse_cache_reprocess_event(event):
    if isinstance(event, dict) and "params" in event and "querystring" in event["params"]:
        event = event["params"]["querystring"]
    if "env" not in event:
        raise ValueError("env querystring is mandatory")
    if "buType" not in event:
        raise ValueError("buType querystring is mandatory")
    if "buId" not in event:
        raise ValueError("buId querystring is mandatory")
    if "objectType" not in event:
        raise ValueError("objectType querystring is mandatory")
    return (
        event["env"],
        event["buType"],
        event["buId"],
        event["objectType"],
    )


def invalidate_patient_detail_cache_from_event(event):
    """
    Fast path: resolve patient (MySQL) and UNLINK known combined-detail keys (no SCAN).
    Heavy SCAN + warm-up runs in run_background_cache_regeneration.
    """
    t_all = time.perf_counter()
    t0 = time.perf_counter()
    _env, bu_type, bu_id, object_type = _parse_cache_reprocess_event(event)
    _log_stage("sync_parse_event", t0)

    if bu_type != "Patient":
        raise ValueError(f"Unsupported buType for cache reprocess: {bu_type}")

    t0 = time.perf_counter()
    patient = resolve_patient(bu_id)
    subject_id, email = patient['subjectId'], patient['email']
    # Callers may send either the numeric id or the subjectId; key building needs the
    # numeric id in the bu_id slot so both cache-key variants get invalidated.
    bu_id = str(patient['patientId'])
    _log_stage("sync_mysql_patient_lookup", t0, f"buId={bu_id}")

    t0 = time.perf_counter()
    explicit_keys = build_explicit_combined_detail_keys(
        object_type, subject_id, bu_id, email
    )
    _log_stage("sync_build_explicit_keys", t0, f"count={len(explicit_keys)} objectType={object_type}")

    t0 = time.perf_counter()
    batch_unlink_cache_keys(explicit_keys)
    _log_stage("sync_redis_unlink_explicit", t0, f"count={len(explicit_keys)}")

    _log_stage("sync_invalidate_total", t_all, f"objectType={object_type} buId={bu_id}")
    return {
        "explicit_keys": explicit_keys,
        "subject_id": subject_id,
        "bu_id": bu_id,
        "email": email,
        "object_type": object_type,
    }



def safe_detail_call(key):
    try:
        detail_call(key)
    except Exception as e:
        print(f"[safe_detail_call ERROR] key={key} error={e}")


def _safe_header_cleanup(subject_id, bu_id, email):
    try:
        _bg_header_cleanup(subject_id, bu_id, email)
    except Exception as e:
        print(f"[header_cleanup ERROR] {e}")


def run_background_cache_regeneration(
    explicit_keys, subject_id, bu_id, email, object_type
):
    """
    SCAN for any remaining matching detail keys, warm cache for all touched keys,
    then refresh headers. Safe to run after HTTP response (may take tens of seconds).
    """
    print(
        f"[cachereprocess] background=start objectType={object_type} buId={bu_id} "
        f"explicit_keys={len(explicit_keys)}"
    )
    t_bg = time.perf_counter()

    t0 = time.perf_counter()
    stray_keys = del_detail_keys_for_resource(
        object_type, subject_id, bu_id, email, n=2
    )
    _log_stage("background_redis_scan_delete_strays", t0, f"deleted={len(stray_keys)}")

    t0 = time.perf_counter()
    to_warm = list(dict.fromkeys(list(explicit_keys) + list(stray_keys)))

    # LIMIT KEYS
    MAX_KEYS = 8
    to_warm = to_warm[:MAX_KEYS]

    _log_stage("background_merge_warm_key_list", t0, f"to_warm={len(to_warm)}")


    #  PRIORITY WARM (few keys synchronously for fast response)
    priority_keys = to_warm[:3]

    for key in priority_keys:
        try:
            safe_detail_call(key)
        except Exception as e:
            print(f"[priority detail_call ERROR] {e}")

    #  REMAINING KEYS ASYNC (non-blocking, throttled)
    remaining_keys = to_warm[3:]

    for key in remaining_keys:
        _bg_executor.submit(safe_detail_call, key)
        time.sleep(0.05)   # throttle to avoid burst load

    _log_stage("background_submit_detail_tasks", t0, f"count={len(to_warm)}")

    #  HEADER CLEANUP ASYNC

    _bg_executor.submit(_safe_header_cleanup, subject_id, bu_id, email)

    _log_stage(
        "background_phase1_non_blocking",
        t_bg,
        f"to_warm={len(to_warm)} note=detail+header_async",
    )

def resource_type_handler(event, context):
    """Fast invalidate; queue SCAN/warm/header on thread pool (do not block caller)."""
    print(event)
    t0 = time.perf_counter()
    inv = invalidate_patient_detail_cache_from_event(event)
    _bg_executor.submit(
        run_background_cache_regeneration,
        inv["explicit_keys"],
        inv["subject_id"],
        inv["bu_id"],
        inv["email"],
        inv["object_type"],
    )
    _log_stage("lambda_sync_through_submit", t0, "note=background_continues_async")
    return {
        "status": "success",
        "message": "Detail cache invalidated; regeneration queued in background.",
        "invalidated_key_count": len(inv["explicit_keys"]),
        "objectType": inv["object_type"],
        "buId": inv["bu_id"],
        "email": inv["email"],
    }

def reprocess_paritent_id(patient_id):
    subject_id, email = get_patient_details(patient_id)
    
    # Synchronously delete details
    details_keys = del_key_list(["details", patient_id, subject_id, email], 2)

    # Background regeneration of details
    for data_key in details_keys:
        _bg_executor.submit(safe_detail_call, data_key)

    # Background header cleanup and regeneration
    _bg_executor.submit(_bg_header_cleanup, subject_id, patient_id, email)
    


if __name__ == '__main__':

    event = {
        "params": {
            "querystring": {
                "env": "dev",
                "buType": "Patient",
                "buId": "203022",
                "objectType": "Procedure"
            }
        }
    }
    resource_type_handler(event, None)
    #del_key_list(["details_" , "203022", "plant28@gmail.com"], 3)
    #del_key("plant28@gmail.com")
    #header_call("header_26cee431-90ee-a1cb-012e-e475b067a897_sdmuneer@yahoo.com_Y")
    #detail_call("details_Procedure_3f4d5a23-b1ab-2197-fd7c-271d2f89730f_ava.james897@gmail.com_Y__")
