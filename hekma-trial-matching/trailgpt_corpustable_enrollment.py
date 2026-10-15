import json
import logging
from utils.pg_util import pg_transaction

logger = logging.getLogger("enrollment_backfill")


def backfill_enrollment_from_rawjson():

    with pg_transaction() as (_, cur):
        cur.execute("""
            SELECT id, raw_json
            FROM trialgpt_corpus
            WHERE raw_json IS NOT NULL
        """)
        rows = cur.fetchall()

    updated = 0
    skipped = 0
    failed = 0

    for row in rows:
        try:
            raw = row.get("raw_json")

            # handle string / dict
            if isinstance(raw, str):
                raw = json.loads(raw)

            if not raw:
                skipped += 1
                continue

            protocol = raw.get("protocolSection", {})
            design = protocol.get("designModule", {})
            enrollment_info = design.get("enrollmentInfo", {})

            if not enrollment_info:
                skipped += 1
                continue

            enrollment = {
                "count": enrollment_info.get("count"),
                "type": enrollment_info.get("type")
            }

            with pg_transaction(dict_cursor=False) as (_, cursor):
                cursor.execute(
                    """
                    UPDATE trialgpt_corpus
                    SET enrollment = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        json.dumps(enrollment),
                        row["id"],
                    ),
                )

            updated += 1

        except Exception as e:
            failed += 1
            logger.error(f"Enrollment backfill failed for id={row.get('id')}: {str(e)}")

    return {
        "total": len(rows),
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
    }





if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    logger.info("Starting enrollment backfill...")

    result = backfill_enrollment_from_rawjson()

    logger.info(f"Completed: {result}")
    print(result)