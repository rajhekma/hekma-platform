import requests
import json
import logging
import time

from utils.pg_util import pg_transaction   

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("raw_backfill")

CLINICAL_API = "https://clinicaltrials.gov/api/v2/studies/{}?format=json&markupFormat=legacy"


def fetch_trial(nct_id):
    response = requests.get(
        CLINICAL_API.format(nct_id),
        headers={"accept": "application/json"}
    )

    if response.status_code != 200:
        raise Exception(f"API failed for {nct_id}")

    return response.json()


def get_nct_ids():
    with pg_transaction(dict_cursor=False) as (conn, cur):
        cur.execute("""
            SELECT DISTINCT nct_id
            FROM trialgpt_corpus
            WHERE nct_id IS NOT NULL
        """)
        rows = cur.fetchall()

    return [r[0] for r in rows]


def upsert_raw(nct_id, raw_json):
    with pg_transaction() as (conn, cur):
        query = """
            INSERT INTO trialgpt_clinicaltrials_raw (nct_id, raw_json)
            VALUES (%s, %s)
            ON CONFLICT (nct_id)
            DO UPDATE SET raw_json = EXCLUDED.raw_json
        """

        cur.execute(query, (nct_id, json.dumps(raw_json)))


def backfill():
    nct_ids = get_nct_ids()

    logger.info(f"Total NCT IDs: {len(nct_ids)}")

    for i, nct_id in enumerate(nct_ids):
        try:
            data = fetch_trial(nct_id)
            upsert_raw(nct_id, data)

            if i % 20 == 0:
                logger.info(f"Processed {i} records")

            time.sleep(0.2)  

        except Exception as e:
            logger.error(f"Failed for {nct_id}: {str(e)}")


if __name__ == "__main__":
    backfill()