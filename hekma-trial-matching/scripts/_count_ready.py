import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from repositories.compose_repo import COMPOSE_READ_TABLE
from utils.pg_util import pg_transaction

with pg_transaction() as (_, cur):
    cur.execute("SELECT COUNT(*) AS n FROM trialgpt_eligible_patients")
    total = cur.fetchone()["n"]
    cur.execute(
        """
        SELECT COUNT(*) AS n
        FROM trialgpt_eligible_patients
        WHERE structured_json IS NOT NULL
          AND summary_text IS NOT NULL
          AND BTRIM(summary_text) <> ''
        """
    )
    ready = cur.fetchone()["n"]

print("table:", COMPOSE_READ_TABLE)
print("total_rows:", total)
print("ready_summaries:", ready)
