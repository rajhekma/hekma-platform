from datetime import datetime
import json

from fastapi import HTTPException

from ..awsutils.postgresql_utils import pg_transaction
from ..redis_service import del_key


def resource_type_handler_healthkit_post(body: dict):
    try:
        source_id = body.get("id")
        ts = body.get("timestamp")

        if not source_id or not ts:
            raise HTTPException(
                status_code=400,
                detail="Both 'id' and 'timestamp' are required",
            )

        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)

        doc_id = f"{source_id}_{str(ts).replace(' ', '')}"

        with pg_transaction() as (_, cur):
            cur.execute(
                """
                INSERT INTO healthkit (doc_id, id, timestamp, payload)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (doc_id)
                DO UPDATE SET
                    payload = EXCLUDED.payload,
                    timestamp = EXCLUDED.timestamp
                """,
                (doc_id, source_id, ts, json.dumps(body)),
            )

        try:
            del_key(f"healthkit_{source_id}")
        except Exception:
            pass

        return {"message": "Success"}

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Issue with healthkit write. Contact administrator.",
        )
