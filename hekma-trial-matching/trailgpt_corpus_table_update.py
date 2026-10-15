import json
import logging

from utils.pg_util import pg_transaction
from services.trial_ingestion_services import fetch_trial_from_clinical_gov  


logger = logging.getLogger("trial_backfill")


def _norm(value):
    return " ".join(str(value).split()).strip().lower() if value else ""


def _location_key(city=None, state=None, country=None, zip_code=None, institute=None):
    return (
        _norm(city),
        _norm(state),
        _norm(country),
        _norm(zip_code),
        _norm(institute),
    )


def _raw_location_contacts(raw_location):
    return [
        {
            "name": c.get("name"),
            "role": c.get("role"),
            "phone": c.get("phone"),
            "email": c.get("email"),
        }
        for c in (raw_location.get("contacts") or [])
    ]


def _build_raw_location_map(protocol_section):
    contacts_module = protocol_section.get("contactsLocationsModule", {})
    raw_locations = contacts_module.get("locations", []) or []

    location_map = {}
    for loc in raw_locations:
        key = _location_key(
            city=loc.get("city"),
            state=loc.get("state"),
            country=loc.get("country"),
            zip_code=loc.get("zip"),
            institute=loc.get("facility"),
        )
        location_map[key] = _raw_location_contacts(loc)

    return location_map


def _find_contacts_for_existing_location(existing_loc, raw_location_map):
    candidates = [
        _location_key(
            city=existing_loc.get("city"),
            state=existing_loc.get("state"),
            country=existing_loc.get("country"),
            zip_code=existing_loc.get("zip_code"),
            institute=existing_loc.get("institute"),
        ),
        _location_key(
            city=existing_loc.get("city"),
            state=existing_loc.get("state"),
            country=existing_loc.get("country"),
            zip_code=existing_loc.get("zip_code"),
        ),
        _location_key(
            city=existing_loc.get("city"),
            state=existing_loc.get("state"),
            country=existing_loc.get("country"),
        ),
        _location_key(
            city=existing_loc.get("city"),
            country=existing_loc.get("country"),
        ),
        _location_key(city=existing_loc.get("city")),
    ]

    for key in candidates:
        if key in raw_location_map:
            return raw_location_map[key]

    return []


def _merge_contacts_into_locations_detailed(existing_locations_detailed, protocol_section):
    raw_location_map = _build_raw_location_map(protocol_section)
    merged = []

    for loc in existing_locations_detailed or []:
        new_loc = dict(loc)  # keep existing fields as-is
        new_loc["contacts"] = _find_contacts_for_existing_location(loc, raw_location_map)
        merged.append(new_loc)

    return merged


def backfill_trialgpt_corpus():
    """
    One-time backfill:
    - raw_json
    - overall_status
    - start_date
    - completion_date
    - locations_detailed.contacts
    """

    with pg_transaction() as (_, cur):
        cur.execute("""
            SELECT id, nct_id, locations_detailed
            FROM trialgpt_corpus
            WHERE nct_id IS NOT NULL
        """)
        rows = cur.fetchall()

    updated = 0
    failed = 0

    for row in rows:
        nct_id = row["nct_id"]

        try:
            body = fetch_trial_from_clinical_gov(nct_id)
            protocol = body.get("protocolSection", {})

            status_module = protocol.get("statusModule", {})
            overall_status = status_module.get("overallStatus")
            start_date = status_module.get("startDateStruct", {}).get("date")
            completion_date = status_module.get("completionDateStruct", {}).get("date")

            existing_locations_detailed = row.get("locations_detailed") or []
            merged_locations_detailed = _merge_contacts_into_locations_detailed(
                existing_locations_detailed,
                protocol,
            )

            with pg_transaction(dict_cursor=False) as (_, cursor):
                cursor.execute(
                    """
                    UPDATE trialgpt_corpus
                    SET raw_json = %s,
                        overall_status = %s,
                        start_date = %s,
                        completion_date = %s,
                        locations_detailed = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        json.dumps(body),
                        overall_status,
                        start_date,
                        completion_date,
                        json.dumps(merged_locations_detailed),
                        row["id"],
                    ),
                )

            updated += 1

        except Exception as e:
            failed += 1
            logger.error(f"Backfill failed for {nct_id}: {str(e)}")

    return {
        "total": len(rows),
        "updated": updated,
        "failed": failed,
    }



if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    logger.info("Starting backfill process...")

    result = backfill_trialgpt_corpus()

    logger.info(f"Backfill completed: {result}")
    print(result)