"""Find MySQL patientIds whose subjectId has a ready summary in Postgres."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()

from utils.pg_util import pg_transaction
from repositories.mysql_repo import get_mysql_connection

# 1) ready subjects (have summary_text) from Postgres
with pg_transaction(dict_cursor=True) as (_, cur):
    cur.execute(
        """
        SELECT subject_id
        FROM trialgpt_eligible_patients
        WHERE summary_text IS NOT NULL AND BTRIM(summary_text) <> ''
        LIMIT 500
        """
    )
    ready = [r["subject_id"] for r in (cur.fetchall() or [])]

print(f"ready subjects sampled: {len(ready)}")

# 2) map back to MySQL patientId
conn = get_mysql_connection()
cur = conn.cursor(dictionary=True)
fmt = ",".join(["%s"] * len(ready))
cur.execute(
    f"SELECT patientId, subjectId FROM Patient WHERE subjectId IN ({fmt}) LIMIT 10",
    ready,
)
rows = cur.fetchall()
cur.close()
conn.close()

print("valid patientId -> subjectId (has summary):")
for r in rows:
    print(f"  patientId={r['patientId']}  subjectId={r['subjectId']}")
if not rows:
    print("  (none found - MySQL Patient has no rows for these ready subjects)")
