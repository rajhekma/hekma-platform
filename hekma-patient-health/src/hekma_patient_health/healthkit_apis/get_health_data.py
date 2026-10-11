from datetime import datetime
import json
import math

from fastapi import HTTPException

from ..awsutils.postgresql_utils import pg_transaction
from ..redis_service import get_key, set_key


def resource_type_handler_healthkit(
    doc_id: str,
    sort_field: str = "timestamp",
    sort_order: str = "asc",
    page: int = 1,
    size: int = 1000,
    from_timestamp: str | None = None,
    to_timestamp: str | None = None,
):
    try:
        if not doc_id:
            raise HTTPException(status_code=400, detail="Missing querystring id")

        if sort_order not in ("asc", "desc"):
            raise HTTPException(
                status_code=400,
                detail='Invalid sort_order. Must be "asc" or "desc"',
            )

        if page < 1 or size < 1:
            raise HTTPException(
                status_code=400,
                detail="page and size must be positive integers",
            )

        parsed_from = None
        if from_timestamp is not None:
            try:
                parsed_from = datetime.fromisoformat(from_timestamp)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid from_timestamp. Must be ISO-8601 datetime",
                )

        parsed_to = None
        if to_timestamp is not None:
            try:
                parsed_to = datetime.fromisoformat(to_timestamp)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid to_timestamp. Must be ISO-8601 datetime",
                )

        if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
            raise HTTPException(
                status_code=400,
                detail="from_timestamp must be less than or equal to to_timestamp",
            )

        offset = (page - 1) * size
        from_key = from_timestamp if from_timestamp is not None else "none"
        to_key = to_timestamp if to_timestamp is not None else "none"
        redis_key = (
            f"healthkit_{doc_id}_{sort_field}_{sort_order}_{page}_{size}_{from_key}_{to_key}"
        )

        try:
            redis_exist, redis_result = get_key(redis_key)
            if redis_exist == 1:
                return json.loads(redis_result)
        except Exception:
            pass

        allowed_sort_fields = {"timestamp": "timestamp", "created_at": "created_at"}
        order_column = allowed_sort_fields.get(sort_field)
        if not order_column:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid sort_field: {sort_field}",
            )

        where_clause = "WHERE id = %s"
        count_params = [doc_id]
        select_params = [doc_id]

        if parsed_from is not None:
            where_clause += " AND timestamp >= %s"
            count_params.append(parsed_from)
            select_params.append(parsed_from)

        if parsed_to is not None:
            where_clause += " AND timestamp <= %s"
            count_params.append(parsed_to)
            select_params.append(parsed_to)

        select_params.extend([size, offset])

        with pg_transaction(dict_cursor=False) as (_, cur):
            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM healthkit
                {where_clause}
                """,
                tuple(count_params),
            )
            total = cur.fetchone()[0]

            cur.execute(
                f"""
                SELECT payload
                FROM healthkit
                {where_clause}
                ORDER BY {order_column} {sort_order}
                LIMIT %s OFFSET %s
                """,
                tuple(select_params),
            )
            rows = cur.fetchall()

        result = {
            "data": [row[0] for row in rows],
            "total": total,
            "size": len(rows),
            "page": page,
            "total_pages": math.ceil(total / size) if size else 0,
        }

        try:
            set_key(redis_key, json.dumps(result))
        except Exception:
            pass

        return result

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Issue with healthkit read. Contact administrator.",
        )
