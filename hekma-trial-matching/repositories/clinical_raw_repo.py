import json
from utils.mysql_util import mysql_cursor


def upsert_raw_trial(nct_id, raw_json):
    with mysql_cursor(dictionary=False) as cursor:
        query = """
            INSERT INTO trialgpt_clinicaltrials_raw (nct_id, raw_json)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE raw_json = VALUES(raw_json)
        """

        cursor.execute(query, (nct_id, json.dumps(raw_json)))