#from ...awsutils.elasticsearch_utils import ElasticSearchConnection
import json
import os
import concurrent.futures
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

from ...awsutils.postgresql_utils import pg_transaction
from ...redis_service import *
from ...awsutils.mysql_db_connection import mysql_connection
from ...ehr_apis.ctms_patient_ids import (
    ARCHIVED_ROW_PREDICATE,
    append_id_only_scope,
    build_ctms_sql,
    normalize_identifier,
    resolve_chart_patient_id,
    resolve_ctms_patient_ids,
)
from ...ehr_apis.fhir_source_filters import (
    EHR_SOURCE_PREDICATE,
    HEKMA_ACTIVE_PREDICATE,
    HEKMA_SOURCE_PREDICATE,
    INTERNAL_TO_TABLE,
)
from ...ehr_apis.get_resource_type_detail.lambda_main import (
    es_index_map,
)
from ...ehr_apis.bmi_rows import count_bmi_rows

file_path = BASE_DIR.parent / "get_resource_type_detail" / "integrate.json"

#os.environ["DISABLE_REDIS"] = "Y"




# def process_resource(resource_type, patient_id, hekma_mail, es_index_map, mapping_json):
#     """
#     Processes a single resource_type and returns a dict with the relevant data entries.
#     Handles both internal and non-internal types, including special cases for Observation.
#     """
#     try:
#         if "Internal" in resource_type:
#             obj = mapping_json["mapping"][resource_type]
#             count = get_count_internals(obj["sql"].format(patient_id, hekma_mail))
#             return {resource_type: count}
#         else:
#             index_name = es_index_map.get(resource_type).get('index')
#             patient_field = es_index_map.get(resource_type).get('patient_field')
#             count = get_count(
#                 index_name=index_name,
#                 patient_id=patient_id,
#                 hekma_mail=hekma_mail,
#                 patient_field=patient_field
#             )
#             result = {resource_type: count}

#             if resource_type in ["Observation", "Observation_CMS"]:
#                 sub_count = get_count_lab(
#                     index_name=index_name,
#                     patient_id=patient_id,
#                     hekma_mail=hekma_mail,
#                     patient_field=patient_field
#                 )
#                 result[resource_type + "_sub"] = sub_count

#             return result
#     except Exception as e:
#         print(f"Error processing {resource_type}: {str(e)}")
#         return {resource_type: 0}  # Or handle as needed

# def is_all_zero_response(response):
#     """
#     Returns True if all numeric values in the response
#     (including nested dicts) are zero.
#     Non-numeric values are ignored.
#     """

#     numeric_found = False

#     def check(obj):
#         nonlocal numeric_found

#         if isinstance(obj, dict):
#             for v in obj.values():
#                 if not check(v):
#                     return False
#             return True

#         elif isinstance(obj, (int, float)):
#             numeric_found = True
#             return obj == 0

#         else:
#             # Ignore strings, None, lists, etc.
#             return True

#     result = check(response)

#     # If no numeric values found at all, do NOT treat as empty
#     if not numeric_found:
#         return False

#     return result


def pg_count_observation_split_json(table="fastenhealth_observation", patient_id=None, hekma_mail=None):
    pid_column = "id" if table == "patient" else "patient_id"
    with pg_transaction(dict_cursor=True) as (_, cursor):

        where = []
        params = {}

        # fastenhealth uses hekma_mail_id
        email_column = "hekma_mail_id"

        if not append_id_only_scope(
            where, params, pid_column=pid_column, patient_id=patient_id, param_key="pid"
        ):
            return {"laboratory_count": 0, "vital_signs_count": 0}

        where_sql = " AND ".join(where) if where else "TRUE"

        sql = f"""
            SELECT
                raw_resource->'category'->0->'coding'->0->>'code' AS category_code,
                COUNT(*) AS cnt
            FROM {table}
            WHERE {where_sql}
              AND {EHR_SOURCE_PREDICATE}
              AND raw_resource ? 'category'
            GROUP BY category_code
        """

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        result = {
            "laboratory_count": 0,
            "vital_signs_count": 0
        }

        for row in rows:
            if row["category_code"] == "laboratory":
                result["laboratory_count"] = row["cnt"]
            elif row["category_code"] == "vital-signs":
                result["vital_signs_count"] = row["cnt"]

        return result



def _medication_patient_id_candidates(patient_id=None, hekma_mail=None, ctms_patient_ids=None):
    """
    Build identifier variants used in medications.patient_id (VARCHAR).
    Adherence meds are typically stored under the CTMS numeric patientId string;
    header callers may also send subjectId / email.
    """
    candidates = []

    def _add(value):
        if value is None:
            return
        text = str(value).strip()
        if text and text not in candidates:
            candidates.append(text)

    _add(patient_id)
    for pid in ctms_patient_ids or []:
        _add(pid)

    return candidates


def pg_count_hekma_medications(patient_id=None, hekma_mail=None, ctms_patient_ids=None):
    """Count rows in Postgres medications (adherence module)."""
    ids = _medication_patient_id_candidates(patient_id, hekma_mail, ctms_patient_ids)
    if not ids:
        return 0

    with pg_transaction(dict_cursor=False) as (_, cursor):
        cursor.execute(
            f"""
            SELECT COUNT(*)
            FROM medications
            WHERE patient_id = ANY(%(ids)s)
              AND {ARCHIVED_ROW_PREDICATE}
            """,
            {"ids": ids},
        )
        return cursor.fetchone()[0]


def process_resource(resource_type, patient_id, hekma_mail, mapping_json, ctms_patient_ids=None):
    try:
        # Internal (CTMS)
        if "Internal" in resource_type:
            if resource_type == "InternalMedication":
                if not ctms_patient_ids:
                    return {resource_type: 0}
                obj = mapping_json["mapping"][resource_type]
                count = get_count_internals(build_ctms_sql(obj["sql"], ctms_patient_ids))
                return {resource_type: count}
            spec = INTERNAL_TO_TABLE.get(resource_type)
            if not spec:
                return {resource_type: 0}
            table, category = spec
            count = pg_count(
                table=table,
                patient_id=patient_id,
                hekma_mail=hekma_mail,
                source_mode="hekma",
                observation_category=category,
                ctms_patient_ids=ctms_patient_ids,
            )
            return {resource_type: count}

        # Postgres adherence medications (medications table)
        if resource_type == "HekmaMedication":
            count = pg_count_hekma_medications(
                patient_id=patient_id,
                hekma_mail=hekma_mail,
                ctms_patient_ids=ctms_patient_ids,
            )
            return {resource_type: count}

        # Computed BMI (fastenhealth_bmi_data, written by hekma_api)
        if resource_type == "HekmaBmi":
            bmi_ids = list(ctms_patient_ids or [])
            if patient_id:
                bmi_ids.append(patient_id)
            return {resource_type: count_bmi_rows(bmi_ids)}

        # PostgreSQL-backed resources
        table = es_index_map.get(resource_type, {}).get("index")
        if not table:
            return {resource_type: 0}

        count = pg_count(
            table=table,
            patient_id=patient_id,
            hekma_mail=hekma_mail,
            source_mode="ehr" if str(table).startswith("fastenhealth_") else "all",
        )

        result = {resource_type: count}

        # Observation Split Logic
        if resource_type == "Observation":
            try:
                result[resource_type + "_sub"] = pg_count_observation_split(
                    table=table,
                    patient_id=patient_id,
                    hekma_mail=hekma_mail
                )
            except Exception as e:
                print(f"Split failed for Observation: {e}")

        elif resource_type == "fastenhealth_observation":
            try:
                result[resource_type + "_sub"] = pg_count_observation_split_json(
                    table=table,
                    patient_id=patient_id,
                    hekma_mail=hekma_mail
                )
            except Exception as e:
                print(f"Split failed for fastenhealth_observation: {e}")

        return result

    except Exception as e:
        print(f"Error processing {resource_type}: {e}")
        return {resource_type: 0}


def update_combined(resource_type, data, mapping_json, combined):
    """
    Updates the combined dict for a given resource_type using the collected data.
    This is called sequentially after parallel data collection.
    """
    if resource_type + "_sub" in data:
        has_sub = True
    else:
        has_sub = False

    for a in mapping_json.keys():
        if resource_type in mapping_json[a]:
            if a in combined:
                combined[a] = data[resource_type] + combined[a]
                if has_sub:
                    if a + "_sub" in combined:
                        sub_dict = {}
                        for b in data[resource_type + "_sub"].keys():
                            sub_dict[b] = combined[a + "_sub"][b] + data[resource_type + "_sub"][b]
                        combined[a + "_sub"] = sub_dict
                    else:
                        combined[a + "_sub"] = data[resource_type + "_sub"].copy()
            else:
                combined[a] = data[resource_type]
                if has_sub:
                    combined[a + "_sub"] = data[resource_type + "_sub"].copy()

def get_count_internals(sql):
    with mysql_connection() as mysql:
        cursor = mysql.cursor(dictionary=True)
        count_sql = "select count(*) cnt from (" + sql + ") as a"
        cursor.execute(count_sql)
        rows = cursor.fetchall()
        return rows[0]["cnt"]




# def get_count(index_name, patient_id = None, patient_field="subject.reference.keyword", hekma_mail = None):
#     es = ElasticSearchConnection()
#     body = {
#           "size": 0,
#           "query": {
#             "match": {
#             }
#           }
#         }
#     if patient_id and hekma_mail:
#         should = list()
#         should.append({
#             "match": {
#                 patient_field: "Patient/" + patient_id
#             }
#         }
#         )
#         should.append({
#             "match": {
#                 "hekma_mail.keyword": hekma_mail
#             }
#         }
#         )
#         body['query'] = {
#             "bool": {
#                 "should": should
#             }
#         }
#     elif hekma_mail:
#         body['query']['match']['hekma_mail.keyword'] = hekma_mail
#     else:
#         body['query']['match'][patient_field] = "Patient/" + patient_id
#     print(body)
#     response = es.search(index=index_name, body=body)
#     return response['hits']['total']['value']

# PostgreSQL COUNT HELPERS
# -------------------------

def pg_count(
    table,
    patient_id=None,
    hekma_mail=None,
    source_mode="all",
    observation_category=None,
    ctms_patient_ids=None,
):
    pid_column = "id" if table == "patient" else "patient_id"
    with pg_transaction(dict_cursor=False) as (_, cursor):

        where = []
        params = {}

        if table.startswith("fastenhealth_") and source_mode == "hekma":
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
                return 0
            keys = []
            for i, pid in enumerate(id_candidates):
                key = f"hekma_pid_{i}"
                params[key] = pid
                keys.append(f"%({key})s")
            where.append(f"{pid_column} IN ({', '.join(keys)})")
            where.append(ARCHIVED_ROW_PREDICATE)
            where.append(HEKMA_SOURCE_PREDICATE)
            where.append(HEKMA_ACTIVE_PREDICATE)
        else:
            if not append_id_only_scope(
                where, params, pid_column=pid_column, patient_id=patient_id, param_key="pid"
            ):
                return 0
            if table.startswith("fastenhealth_") and source_mode == "ehr":
                where.append(EHR_SOURCE_PREDICATE)

        if observation_category:
            where.append(
                "raw_resource->'category'->0->'coding'->0->>'code' = %(obs_cat)s"
            )
            params["obs_cat"] = observation_category

        where_sql = " AND ".join(where) if where else "TRUE"

        sql = f"""
            SELECT COUNT(*)
            FROM {table}
            WHERE {where_sql}
        """

        cursor.execute(sql, params)
        return cursor.fetchone()[0]


# def get_count_lab(index_name, patient_id = None, patient_field="subject.reference.keyword", hekma_mail = None):
#     es = ElasticSearchConnection()
#     con = {}
#     if patient_id and hekma_mail:
#         should = list()
#         should.append({
#             "match": {
#                 patient_field: "Patient/" + patient_id
#             }
#         }
#         )
#         should.append({
#             "match": {
#                 "hekma_mail.keyword": hekma_mail
#             }
#         }
#         )
#         con = {"bool": {"should": should}}
#     elif hekma_mail:
#         con = {
#             "term": {
#                 "hekma_mail.keyword": {
#                     "value": hekma_mail
#                 }
#             }
#         }
#     else:
#         con = {
#             "term": {
#                 patient_field: {
#                     "value": "Patient/" + patient_id
#                 }
#             }
#         }

#     lab_sub_list = ["laboratory", "vital-signs"]
#     dict_count = {}
#     for sub_type in lab_sub_list:
#         body = {
#           "size": 0,
#           "query": {
#             "bool": {
#               "must": [
#                 con,
#                 {
#                   "term": {
#                     "category.coding.code.keyword": {
#                       "value": sub_type
#                     }
#                   }
#                 }
#               ]
#             }
#           }
#         }
#         print(body)
#         response = es.search(index=index_name, body=body)
#         dict_count[sub_type.replace("-", "_") + "_count"] = response['hits']['total']['value']
#     return dict_count

def pg_count_observation_split(table="observation", patient_id=None, hekma_mail=None):
    pid_column = "id" if table == "patient" else "patient_id"
    with pg_transaction(dict_cursor=True) as (_, cursor):
        where = []
        params = {}

        if not append_id_only_scope(
            where, params, pid_column=pid_column, patient_id=patient_id, param_key="pid"
        ):
            return {"laboratory_count": 0, "vital_signs_count": 0}

        where_sql = " AND ".join(where) if where else "TRUE"

        sql = f"""
            SELECT category_code, COUNT(*) cnt
            FROM {table}
            WHERE {where_sql}
            GROUP BY category_code
        """

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        result = {
            "laboratory_count": 0,
            "vital_signs_count": 0
        }

        for row in rows:
            if row["category_code"] == "laboratory":
                result["laboratory_count"] = row["cnt"]
            elif row["category_code"] == "vital-signs":
                result["vital_signs_count"] = row["cnt"]

        return result



# def get_details(patient_id: str = None, hekma_mail: str = None, combined_flag: str = "N", lab_split: str = "N"):
#     mapping_json = None
#     if combined_flag == "Y":
#         #with open("C:\\Users\\shank\\Desktop\\GIT\\hekmagithub\\hekma_data_pipleline\\ehr_apis\\get_resource_type_detail\\integrate.json", "r") as f:
#         #with open("../get_resource_type_detail/integrate.json", "r") as f:
#         with open("./ehr_apis/get_resource_type_detail/integrate.json", "r") as f:
#             mapping_json = json.loads(f.read())
#     data = dict()
#     combined = dict()

#     resource_types = list(es_index_map.keys()) + [
#         "InternalCondition",
#         "InternalProcedure",
#         "InternalImmunization",
#         "InternalObservationVital",
#         "InternalMedication",
#         "InternalAllergyIntolerance",
#         "InternalObservation"]
#     max_workers = min(20, len(resource_types))  # Adjust based on your system's capacity and number of resources

#     with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
#         # Submit all tasks
#         futures = [
#             executor.submit(process_resource, rt, patient_id, hekma_mail, es_index_map, mapping_json)
#             for rt in resource_types
#         ]

#         # Collect results as they complete (non-blocking)
#         for future in concurrent.futures.as_completed(futures):
#             try:
#                 partial_data = future.result()
#                 data.update(partial_data)
#                 # Optional: logger.info(f"Completed: {list(partial_data.keys())}")
#             except Exception as e:
#                 print(f"Future failed: {str(e)}")

#     # Now perform the combined updates sequentially (lightweight, no parallelism needed)
#     if combined_flag == "Y":
#         for resource_type in resource_types:
#             update_combined(resource_type, data, mapping_json, combined)

#     if combined_flag == "Y":
#         data["combined"] = combined
#     return data

def get_details(patient_id=None, hekma_mail=None, combined_flag="N", jwt_user_id=None):
    mapping_json = None
    if combined_flag == "Y":

        with open(file_path, "r") as f:
            mapping_json = json.loads(f.read())

    patient_id = resolve_chart_patient_id(patient_id, hekma_mail, jwt_user_id)
    hekma_mail = None
    ctms_patient_ids = resolve_ctms_patient_ids(patient_id, None)

    data = {}
    combined = {}

    resource_types = list(es_index_map.keys()) + [
        "InternalCondition",
        "InternalProcedure",
        "InternalImmunization",
        "InternalObservationVital",
        "InternalMedication",
        "InternalAllergyIntolerance",
        "InternalObservation",
        "HekmaMedication",
        "HekmaBmi",
    ]

    max_workers = min(
        int(os.getenv("HEADER_MAX_WORKERS", "8")),
        len(resource_types),
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                process_resource,
                rt,
                patient_id,
                hekma_mail,
                mapping_json,
                ctms_patient_ids
            )
            for rt in resource_types
        ]

        for future in concurrent.futures.as_completed(futures):
            data.update(future.result())

    if combined_flag == "Y":
        for rt in resource_types:
            update_combined(rt, data, mapping_json, combined)
        data["combined"] = combined

    return data



def resource_type_handler(event, context):

    if isinstance(event, dict) and "params" in event and "querystring" in event["params"]:
        event = event["params"]["querystring"]

    patientId = None
    hekma_mail = None
    combinedFlag = "N"

    if 'hekmaMail' in event:
        hekma_mail = normalize_identifier(event['hekmaMail'])
    if 'patientId' in event:
        patientId = normalize_identifier(event['patientId'])
    if 'combinedFlag' in event:
        combinedFlag = event['combinedFlag']
    jwt_user_id = None
    if "jwtUserId" in event:
        jwt_user_id = normalize_identifier(event["jwtUserId"])

    chart_id = resolve_chart_patient_id(patientId, hekma_mail, jwt_user_id)

    # redis key — resolved patient id only (never email)
    redis_key="header"
    if chart_id:
        redis_key = redis_key + "_" + chart_id
    else:
        redis_key = redis_key + "_"
    redis_key = redis_key + "_"
    if combinedFlag:
        redis_key = redis_key + "_" + combinedFlag
    else:
        redis_key = redis_key + "_"

    if os.getenv("DISABLE_REDIS") == "Y":
        print("Redis disabled - returning fresh data")
        response = get_details(
            patient_id=chart_id,
            hekma_mail=None,
            combined_flag=combinedFlag,
            jwt_user_id=jwt_user_id,
        )
        return response

    try:
        redis_exist, redis_result = get_key(redis_key)
    except Exception as e:
        print("Redis not exist" + str(e))
        redis_exist = None

    if redis_exist and redis_exist == 1:
        print("Redis data exist!!")
        print(redis_result)
        return json.loads(redis_result)

    else:
        response = get_details(
            patient_id=chart_id,
            hekma_mail=None,
            combined_flag=combinedFlag,
            jwt_user_id=jwt_user_id,
        )
        set_key(redis_key, json.dumps(response))

        # if not is_all_zero_response(response):
        #     set_key(redis_key, json.dumps(response))
        # else:
        #     print("Skipping Redis cache — all values are zero")
        return response

if __name__ == '__main__':
    print(get_details(patient_id='0e109e66-4f48-9720-1eb8-5179b11227a2', hekma_mail='avajame.s897@gmail.com', combined_flag="Y"))
    quit(0)
    path="../get_resource_type_detail/integrate.json"
    #path="/ehr_apis/get_resource_type_detail/integrate.json"
    combined_result = {}
    with open(path, "r") as f:
        mapping_json = json.loads(f.read())

    print(mapping_json)
    for a in mapping_json.keys():
        print(a)










        