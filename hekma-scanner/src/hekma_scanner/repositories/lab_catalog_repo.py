from typing import Any, Dict, List, Optional, Tuple

from ..awsutils.postgresql_utils import pg_transaction


API_TO_DB_COLUMNS = {
    "fieldKey": "field_key",
    "loincCode": "loinc_code",
    "recordType": "record_type",
    "category": "category",
    "displayName": "display_name",
    "dataType": "data_type",
    "conventionalUnit": "conventional_unit",
    "siUnit": "si_unit",
    "conventionalReferenceRange": "conventional_reference_range",
    "siReferenceRange": "si_reference_range",
    "populationNotes": "population_notes",
    "conventionalCriticalRange": "conventional_critical_range",
    "siCriticalRange": "si_critical_range",
    "interpretationRule": "interpretation_rule",
    "sourceStandard": "source_standard",
    "isActive": "is_active",
}


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _tokenize(search: str) -> List[str]:
    return [token for token in search.strip().split() if token]


def _build_filters(
    *,
    record_type: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    include_inactive: bool = False,
) -> Tuple[List[str], List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []

    if not include_inactive:
        clauses.append("is_active = TRUE")
    if record_type:
        clauses.append("record_type = %s")
        params.append(record_type)
    if category:
        clauses.append("category ILIKE %s")
        params.append(category)

    tokens = _tokenize(search) if search else []
    for token in tokens:
        term = f"%{_escape_like(token)}%"
        clauses.append(
            """
            (
                display_name ILIKE %s ESCAPE '\\'
                OR field_key ILIKE %s ESCAPE '\\'
                OR loinc_code ILIKE %s ESCAPE '\\'
                OR category ILIKE %s ESCAPE '\\'
            )
            """
        )
        params.extend([term, term, term, term])

    return clauses, params


def _rank_order_sql(search: Optional[str]) -> Tuple[str, List[Any]]:
    """Prefer prefix matches, then contains matches, for dropdown ranking."""
    if not search or not search.strip():
        return "record_type, category, display_name", []

    raw = search.strip()
    prefix = f"{_escape_like(raw)}%"
    contains = f"%{_escape_like(raw)}%"
    order_sql = """
        CASE
            WHEN display_name ILIKE %s ESCAPE '\\' THEN 0
            WHEN field_key ILIKE %s ESCAPE '\\' THEN 1
            WHEN loinc_code ILIKE %s ESCAPE '\\' THEN 2
            WHEN display_name ILIKE %s ESCAPE '\\' THEN 3
            WHEN category ILIKE %s ESCAPE '\\' THEN 4
            ELSE 5
        END,
        display_name
    """
    return order_sql, [prefix, prefix, prefix, contains, contains]


class LabCatalogRepository:
    def list(
        self,
        *,
        record_type: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        include_inactive: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        clauses, params = _build_filters(
            record_type=record_type,
            category=category,
            search=search,
            include_inactive=include_inactive,
        )
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order_sql, order_params = _rank_order_sql(search)
        params.extend(order_params)
        params.extend([limit, offset])
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                f"""
                SELECT *
                FROM standard_lab_catalog
                {where}
                ORDER BY {order_sql}
                LIMIT %s OFFSET %s
                """,
                tuple(params),
            )
            return cur.fetchall()

    def count(
        self,
        *,
        record_type: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        include_inactive: bool = False,
    ) -> int:
        clauses, params = _build_filters(
            record_type=record_type,
            category=category,
            search=search,
            include_inactive=include_inactive,
        )
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                f"SELECT COUNT(*) AS total FROM standard_lab_catalog {where}",
                tuple(params),
            )
            return int(cur.fetchone()["total"])

    def suggest(
        self,
        *,
        q: str,
        record_type: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Lightweight ranked matches for typeahead dropdowns."""
        clauses, params = _build_filters(
            record_type=record_type,
            category=category,
            search=q,
            include_inactive=False,
        )
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order_sql, order_params = _rank_order_sql(q)
        params.extend(order_params)
        params.append(limit)
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                f"""
                SELECT
                    field_key,
                    loinc_code,
                    record_type,
                    category,
                    display_name,
                    data_type,
                    conventional_unit,
                    si_unit,
                    conventional_reference_range
                FROM standard_lab_catalog
                {where}
                ORDER BY {order_sql}
                LIMIT %s
                """,
                tuple(params),
            )
            return cur.fetchall()

    def list_categories(
        self,
        *,
        record_type: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        clauses, params = _build_filters(
            record_type=record_type,
            include_inactive=include_inactive,
        )
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                f"""
                SELECT
                    category,
                    record_type,
                    COUNT(*) AS item_count
                FROM standard_lab_catalog
                {where}
                GROUP BY category, record_type
                ORDER BY record_type, category
                """,
                tuple(params),
            )
            return cur.fetchall()

    def get(self, field_key: str, include_inactive: bool = False):
        active_clause = "" if include_inactive else " AND is_active = TRUE"
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                f"""
                SELECT * FROM standard_lab_catalog
                WHERE field_key = %s{active_clause}
                """,
                (field_key,),
            )
            return cur.fetchone()

    def create(self, data: Dict[str, Any]):
        columns = [API_TO_DB_COLUMNS[key] for key in data]
        placeholders = ", ".join(["%s"] * len(columns))
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                f"""
                INSERT INTO standard_lab_catalog ({", ".join(columns)})
                VALUES ({placeholders})
                RETURNING *
                """,
                tuple(data.values()),
            )
            return cur.fetchone()

    def update(self, field_key: str, data: Dict[str, Any]):
        assignments = [
            f"{API_TO_DB_COLUMNS[key]} = %s"
            for key in data
            if key != "fieldKey"
        ]
        values = [value for key, value in data.items() if key != "fieldKey"]
        if not assignments:
            return self.get(field_key, include_inactive=True)

        assignments.append("updated_at = NOW()")
        values.append(field_key)
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                f"""
                UPDATE standard_lab_catalog
                SET {", ".join(assignments)}
                WHERE field_key = %s
                RETURNING *
                """,
                tuple(values),
            )
            return cur.fetchone()

    def deactivate(self, field_key: str):
        with pg_transaction(dict_cursor=True) as (_, cur):
            cur.execute(
                """
                UPDATE standard_lab_catalog
                SET is_active = FALSE, updated_at = NOW()
                WHERE field_key = %s AND is_active = TRUE
                RETURNING *
                """,
                (field_key,),
            )
            return cur.fetchone()
