import json
import redis
from .awsutils.elasticsearch_utils import *

#redis_host = "13.200.225.194"
#redis_port = 6379
#pword = "Hekma360"
ttl = 1 * 24 * 60 * 60

# Tracks cache key names; must stay a Redis SET (SADD/SMEMBERS). If it was
# created as a string or other type elsewhere, SADD fails with WRONGTYPE.
KEY_LIST_META = "key_list"

_redis_pool = None

# import multiprocessing
# from functools import partial


def _redis_type(client, key):
    t = client.type(key)
    if isinstance(t, bytes):
        t = t.decode()
    return t


def _ensure_key_list_is_set(client):
    t = _redis_type(client, KEY_LIST_META)
    if t not in ("none", "set"):
        client.delete(KEY_LIST_META)


def _smembers_key_list(client):
    try:
        return client.smembers(KEY_LIST_META)
    except redis.ResponseError as e:
        err = str(e).lower()
        if "wrongtype" in err or "wrong kind" in err:
            client.delete(KEY_LIST_META)
            return set()
        raise

def _is_key_matched(key, prefix, search_terms, required_matches):
    if not key.startswith(prefix):
        return None
        
    if required_matches > 0:
        matches = 0
        for term in search_terms:
            if term in key:
                matches += 1
                if matches >= required_matches:
                    break
        if matches < required_matches:
            return None
    
    return key


# Event types that cache combined patient-detail payloads under deterministic keys
# (must match get_resource_type_detail.lambda_main combinedFlag == "Y" branch).
COMBINED_DETAIL_EVENT_TYPES = frozenset(
    {
        "Condition",
        "Procedure",
        "Immunization",
        "Observation",
        "AllergyIntolerance",
        "MedicationOrder",
    }
)


def _format_combined_detail_redis_key(event_type, patient_id_str, hekma_mail, vital, lab):
    """Mirror redis_key construction in get_resource_type_detail.resource_type_handler."""
    redis_key = "details_" + event_type
    redis_key = redis_key + ("_" + patient_id_str if patient_id_str else "_")
    redis_key = redis_key + ("_" + hekma_mail if hekma_mail else "_")
    redis_key = redis_key + "_Y"
    redis_key = redis_key + ("_" + vital if vital else "_")
    redis_key = redis_key + ("_" + lab if lab else "_")
    return redis_key


def build_explicit_combined_detail_keys(object_type, subject_id, bu_id, email):
    """
    Enumerate combined-cache keys for this patient without SCAN.
    Covers numeric MySQL id, FHIR subject id, and empty patientId variants; for Observation,
    vital/lab query combinations used by clients.
    """
    if object_type not in COMBINED_DETAIL_EVENT_TYPES:
        return []

    patient_slots = []
    for p in (bu_id, subject_id, ""):
        s = str(p) if p is not None else ""
        if s not in patient_slots:
            patient_slots.append(s)

    mail = email or ""

    if object_type == "Observation":
        vit_opts = (None, "Y", "N")
        lab_opts = (None, "Y", "N")
    else:
        vit_opts = (None,)
        lab_opts = (None,)

    keys = []
    for ps in patient_slots:
        for v in vit_opts:
            for lb in lab_opts:
                keys.append(
                    _format_combined_detail_redis_key(object_type, ps, mail, v, lb)
                )
    return keys


def batch_unlink_cache_keys(keys):
    """
    Remove string cache keys and drop them from key_list metadata. Uses UNLINK when available.
    Returns count of keys processed (not necessarily keys that existed).
    """
    if not keys:
        return 0
    client = get_redis_client()
    chunk_size = 500
    total = 0
    for i in range(0, len(keys), chunk_size):
        chunk = keys[i : i + chunk_size]
        try:
            client.unlink(*chunk)
        except Exception:
            client.delete(*chunk)
        pipe = client.pipeline(transaction=False)
        for k in chunk:
            pipe.srem(KEY_LIST_META, k)
        pipe.execute()
        total += len(chunk)
    return total


def del_detail_keys_for_resource(object_type, subject_id, bu_id, email, n=2):
    """
    Delete detail cache keys for one FHIR/resource type and patient, without loading
    the full key_list set or using multiprocessing (avoids multi-second invalidation).

    Returns the list of deleted key names (for optional background warm-up).
    """
    search_terms = [k for k in (subject_id, bu_id, email) if k]
    required_matches = n - 1
    if required_matches > 0 and len(search_terms) < required_matches:
        return []

    client = get_redis_client()
    prefix = f"details_{object_type}_"
    match_glob = f"details_{object_type}_*"
    deleted_keys = []

    for key in client.scan_iter(match=match_glob, count=500):
        if _is_key_matched(key, prefix, search_terms, required_matches):
            deleted_keys.append(key)

    if deleted_keys:
        chunk_size = 500
        for i in range(0, len(deleted_keys), chunk_size):
            chunk = deleted_keys[i : i + chunk_size]
            pipe = client.pipeline(transaction=False)
            for k in chunk:
                pipe.delete(k)
            pipe.srem(KEY_LIST_META, *chunk)
            pipe.execute()

    return deleted_keys


def get_redis_client():
    global _redis_pool
    if _redis_pool is None:
        credentials = get_redis_credentials()
        _redis_pool = redis.ConnectionPool(
            host=credentials['host'],
            port=credentials['port'],
            password=credentials['password'],
            decode_responses=True,
            max_connections=20
        )
    return redis.Redis(connection_pool=_redis_pool)

def get_key(key):
    client = get_redis_client()
    # Test connection (optional, can be removed in prod for speed)
    # print(client.ping())  # Should return True

    if client.exists(key):
        # print(f"Key '{key}' exists in Redis. Retrieving value...")
        return 1, client.get(key)
    return 0, ""

def set_key(key, value):
    client = get_redis_client()
    if key == KEY_LIST_META:
        print("Redis Set Error: refusing to store cache payload at key_list metadata key")
        return False
    try:
        kt = _redis_type(client, key)
        if kt not in ("none", "string"):
            client.delete(key)
        client.set(key, value, ex=ttl)
        _ensure_key_list_is_set(client)
        client.sadd(KEY_LIST_META, key)
        return True
    except Exception as e:
        print(f"Redis Set Error: {e}")
        return False

def del_key(search_key):
    client = get_redis_client()
    
    # Fetch all keys from the Redis Set (native O(1) removals later)
    all_keys = _smembers_key_list(client)

    if not all_keys:
        return

    deleted_keys = [key for key in all_keys if search_key in key]
    
    # Batch delete and removal from Set
    if deleted_keys:
        chunk_size = 1000
        with client.pipeline() as pipe:
            for i in range(0, len(deleted_keys), chunk_size):
                chunk = deleted_keys[i:i + chunk_size]
                pipe.delete(*chunk)
                pipe.srem(KEY_LIST_META, *chunk)
            pipe.execute()

def del_key_list(key_list, n):
    client = get_redis_client()
    
    # Fetch all keys from the Redis Set
    all_keys = _smembers_key_list(client)

    if not all_keys or not key_list:
        return []

    prefix = key_list[0] + "_"
    search_terms = [k for k in key_list[1:] if k]
    required_matches = n - 1
    
    deleted_keys = []
    for key in all_keys:
        try:
            res = _is_key_matched(
                key,
                prefix=prefix,
                search_terms=search_terms,
                required_matches=required_matches
            )
            if res:
                deleted_keys.append(res)
        except Exception as e:
            print(f"[del_key_list ERROR] {e}")

    if deleted_keys:
        chunk_size = 1000
        with client.pipeline() as pipe:
            for i in range(0, len(deleted_keys), chunk_size):
                chunk = deleted_keys[i:i + chunk_size]
                pipe.delete(*chunk)
                pipe.srem(KEY_LIST_META, *chunk)
            pipe.execute()
        
    return deleted_keys

def update_key_list():
    client = get_redis_client()
    # Pull current keys in one pass
    key_list = [key for key in client.scan_iter("*") if key != KEY_LIST_META]
    
    if key_list:
        with client.pipeline() as pipe:
            # Overwrite existing set to clean up expired keys
            pipe.delete(KEY_LIST_META)
            # SADD in chunks to handle huge counts safely
            chunk_size = 5000
            for i in range(0, len(key_list), chunk_size):
                pipe.sadd(KEY_LIST_META, *key_list[i:i + chunk_size])
            pipe.execute()


if __name__ == '__main__':
    credentials = get_redis_credentials()
    client = redis.Redis(host=credentials['host'], port=credentials['port'],password=credentials['password'],  decode_responses=True
                         )
    email = "plant28@gmail.com"
    for key in _smembers_key_list(client):
        if email in key:
            print(key)

    #update_key_list()
    #set_key("a","b")
    #for key in client.scan_iter("*"):
    #    print(key)
    #    #if '_' in key:
    #        #client.delete(key)
    #        #print(key + " deleted")
