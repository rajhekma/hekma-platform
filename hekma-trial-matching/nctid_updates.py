import json
import time
import requests
import logging

from utils.pg_util import pg_transaction

# ---------------- CONFIG ----------------
CLINICAL_API = "https://clinicaltrials.gov/api/v2/studies/{}?format=json&markupFormat=legacy"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill")


# ---------------- EXISTING EXTRACTION LOGIC (COPY EXACT) ----------------
def extract_locations_and_countries(protocol_section):
    countries = set()
    locations = []
    detailed_locations = []

    contacts_module = protocol_section.get("contactsLocationsModule", {})
    loc_list = contacts_module.get("locations", [])

    for loc in loc_list:
        country = loc.get("country")
        city = loc.get("city")
        state = loc.get("state")
        institute = loc.get("facility")
        zip_code = loc.get("zip")

        geo = loc.get("geoPoint", {})
        lat = geo.get("lat")
        lon = geo.get("lon")

        if country:
            countries.add(country.strip())

        formatted = ", ".join([p for p in [city, state, country] if p])
        if formatted:
            locations.append(formatted)

        detailed_locations.append({
            "institute": institute,
            "city": city,
            "state": state,
            "country": country,
            "zip_code": zip_code,
            "lat": lat,
            "lon": lon
        })

    return list(countries), list(set(locations)), detailed_locations


# ---------------- FETCH ALL NCTIDs ----------------
def fetch_all_nct_ids():
    with pg_transaction() as (_, cur):
        cur.execute("""
            SELECT nct_id
            FROM trialgpt_corpus
            WHERE nct_id IS NOT NULL
        """)
        rows = cur.fetchall()

    return [row["nct_id"] for row in rows]


# ---------------- CALL CLINICAL API ----------------
def fetch_trial(nct_id):
    try:
        response = requests.get(
            CLINICAL_API.format(nct_id),
            headers={"accept": "application/json"},
            timeout=10
        )

        if response.status_code != 200:
            logger.error(f"API failed for {nct_id}")
            return None

        return response.json()

    except Exception as e:
        logger.error(f"Exception for {nct_id}: {str(e)}")
        return None


# ---------------- UPDATE ONLY ONE COLUMN ----------------
def update_locations_detailed(nct_id, detailed_locations):
    with pg_transaction() as (_, cur):
        cur.execute("""
            UPDATE trialgpt_corpus
            SET locations_detailed = %s
            WHERE nct_id = %s
        """, (json.dumps(detailed_locations), nct_id))


# ---------------- MAIN PROCESS ----------------
def run_backfill():

    nct_ids = fetch_all_nct_ids()
    total = len(nct_ids)

    logger.info(f"Total NCTIDs: {total}")

    for idx, nct_id in enumerate(nct_ids, start=1):

        body = fetch_trial(nct_id)
        if not body:
            continue

        protocol = body.get("protocolSection", {})

        # EXACT same extraction
        _, _, detailed_locations = extract_locations_and_countries(protocol)

        # update DB
        update_locations_detailed(nct_id, detailed_locations)

        logger.info(f"Updated {idx}/{total}: {nct_id}")

        # avoid rate limit
        time.sleep(0.1)

    logger.info("Backfill completed!")


# ---------------- RUN ----------------
if __name__ == "__main__":
    run_backfill()