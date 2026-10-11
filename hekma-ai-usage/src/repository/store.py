from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Protocol
from uuid import UUID

from service.pricing import ModelPrice
from api.schemas import UsageEventOut, money


MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class UsageRepository(Protocol):
    def insert_event(self, row: dict[str, Any]) -> bool:
        """Return True if inserted, False if duplicate request_id."""

    def list_prices(self, at: Optional[datetime] = None) -> list[ModelPrice]:
        ...

    def aggregate_patient(
        self,
        *,
        tenant_id: int,
        patient_id: str,
        start: datetime,
        end: datetime,
        product: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        ...

    def list_events(
        self,
        *,
        tenant_id: int,
        patient_id: str,
        start: datetime,
        end: datetime,
        product: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[UsageEventOut]]:
        ...

    def ping(self) -> bool:
        ...


def open_repository(database_url: str):
    """Postgres in production/compose; SQLite when Docker is not available."""
    if database_url.startswith("sqlite:") or database_url == ":memory:":
        from .sqlite import SqliteUsageRepository

        return SqliteUsageRepository(database_url)
    return PostgresUsageRepository(database_url)


class PostgresUsageRepository:
    def __init__(self, database_url: str, minconn: int = 1, maxconn: int = 10) -> None:
        from psycopg2.pool import ThreadedConnectionPool

        self._pool = ThreadedConnectionPool(minconn, maxconn, dsn=database_url)

    def close(self) -> None:
        self._pool.closeall()

    def ping(self) -> bool:
        conn = self._pool.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
            return True
        finally:
            self._pool.putconn(conn)

    def migrate(self) -> None:
        conn = self._pool.getconn()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        filename TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                files = sorted(p for p in MIGRATIONS_DIR.glob("*.sql") if p.is_file())
                for path in files:
                    cur.execute(
                        "SELECT 1 FROM schema_migrations WHERE filename = %s",
                        (path.name,),
                    )
                    if cur.fetchone():
                        continue
                    cur.execute(path.read_text(encoding="utf-8"))
                    cur.execute(
                        "INSERT INTO schema_migrations (filename) VALUES (%s)",
                        (path.name,),
                    )
        finally:
            self._pool.putconn(conn)

    def insert_event(self, row: dict[str, Any]) -> bool:
        sql = """
            INSERT INTO ai_usage_events (
                request_id, tenant_id, patient_id, product, feature,
                provider, model, prompt_tokens, completion_tokens, total_tokens,
                input_cost_usd, output_cost_usd, cost_usd, pricing_status,
                price_version, cached, job_id, source_service, occurred_at,
                schema_version
            ) VALUES (
                %(request_id)s, %(tenant_id)s, %(patient_id)s, %(product)s, %(feature)s,
                %(provider)s, %(model)s, %(prompt_tokens)s, %(completion_tokens)s, %(total_tokens)s,
                %(input_cost_usd)s, %(output_cost_usd)s, %(cost_usd)s, %(pricing_status)s,
                %(price_version)s, %(cached)s, %(job_id)s, %(source_service)s, %(occurred_at)s,
                %(schema_version)s
            )
            ON CONFLICT (request_id) DO NOTHING
        """
        conn = self._pool.getconn()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(sql, row)
                    return cur.rowcount == 1
        finally:
            self._pool.putconn(conn)

    def list_prices(self, at: Optional[datetime] = None) -> list[ModelPrice]:
        conn = self._pool.getconn()
        try:
            from psycopg2.extras import RealDictCursor

            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT provider, model, input_usd_per_1m, output_usd_per_1m,
                           effective_from, effective_to
                    FROM ai_model_prices
                    ORDER BY provider, model, effective_from DESC
                    """
                )
                rows = cur.fetchall()
        finally:
            self._pool.putconn(conn)
        return [
            ModelPrice(
                provider=r["provider"],
                model=r["model"],
                input_usd_per_1m=Decimal(str(r["input_usd_per_1m"])),
                output_usd_per_1m=Decimal(str(r["output_usd_per_1m"])),
                effective_from=_aware(r["effective_from"]),
                effective_to=_aware(r["effective_to"]) if r["effective_to"] else None,
            )
            for r in rows
        ]

    def aggregate_patient(
        self,
        *,
        tenant_id: int,
        patient_id: str,
        start: datetime,
        end: datetime,
        product: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        sql = """
            SELECT
                product,
                provider,
                model,
                COUNT(*)::bigint AS llm_calls,
                COALESCE(SUM(prompt_tokens), 0)::bigint AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0)::bigint AS completion_tokens,
                COALESCE(SUM(total_tokens), 0)::bigint AS total_tokens,
                COALESCE(SUM(cost_usd), 0) AS cost_usd,
                COALESCE(SUM(CASE WHEN pricing_status = 'unpriced' THEN 1 ELSE 0 END), 0)::bigint
                    AS unpriced_calls
            FROM ai_usage_events
            WHERE tenant_id = %s
              AND patient_id = %s
              AND occurred_at >= %s
              AND occurred_at < %s
              AND (%s::text IS NULL OR product = %s)
            GROUP BY GROUPING SETS (
                (),
                (product),
                (provider, model)
            )
        """
        from psycopg2.extras import RealDictCursor

        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    sql,
                    (tenant_id, patient_id, start, end, product, product),
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            self._pool.putconn(conn)

    def list_events(
        self,
        *,
        tenant_id: int,
        patient_id: str,
        start: datetime,
        end: datetime,
        product: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[UsageEventOut]]:
        where = """
            tenant_id = %s AND patient_id = %s
            AND occurred_at >= %s AND occurred_at < %s
            AND (%s::text IS NULL OR product = %s)
        """
        from psycopg2.extras import RealDictCursor

        params = (tenant_id, patient_id, start, end, product, product)
        conn = self._pool.getconn()
        try:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"SELECT COUNT(*) AS n FROM ai_usage_events WHERE {where}", params)
                total = int(cur.fetchone()["n"])
                cur.execute(
                    f"""
                    SELECT request_id, occurred_at, product, feature, provider, model,
                           prompt_tokens, completion_tokens, total_tokens, cost_usd,
                           pricing_status, job_id, source_service
                    FROM ai_usage_events
                    WHERE {where}
                    ORDER BY occurred_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    params + (limit, offset),
                )
                events = [
                    UsageEventOut(
                        request_id=r["request_id"],
                        occurred_at=_aware(r["occurred_at"]),
                        product=r["product"],
                        feature=r["feature"] or "",
                        provider=r["provider"],
                        model=r["model"],
                        prompt_tokens=int(r["prompt_tokens"]),
                        completion_tokens=int(r["completion_tokens"]),
                        total_tokens=int(r["total_tokens"]),
                        cost_usd=money(r["cost_usd"]),
                        pricing_status=r["pricing_status"],
                        job_id=r["job_id"],
                        source_service=r["source_service"],
                    )
                    for r in cur.fetchall()
                ]
                return total, events
        finally:
            self._pool.putconn(conn)


class InMemoryUsageRepository:
    """Used by unit tests — same contract, no Postgres."""

    def __init__(self, prices: Optional[list[ModelPrice]] = None) -> None:
        self._lock = threading.Lock()
        self.events: dict[str, dict[str, Any]] = {}
        self._prices = prices or []

    def ping(self) -> bool:
        return True

    def insert_event(self, row: dict[str, Any]) -> bool:
        key = str(row["request_id"])
        with self._lock:
            if key in self.events:
                return False
            self.events[key] = dict(row)
            return True

    def list_prices(self, at: Optional[datetime] = None) -> list[ModelPrice]:
        return list(self._prices)

    def seed_price(self, price: ModelPrice) -> None:
        self._prices.append(price)

    def aggregate_patient(
        self,
        *,
        tenant_id: int,
        patient_id: str,
        start: datetime,
        end: datetime,
        product: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        rows = self._filtered(tenant_id, patient_id, start, end, product)
        result: list[dict[str, Any]] = []
        result.append(_rollup(rows, product=None, provider=None, model=None))
        by_product: dict[str, list] = defaultdict(list)
        by_model: dict[tuple[str, str], list] = defaultdict(list)
        for row in rows:
            by_product[row["product"]].append(row)
            by_model[(row["provider"], row["model"])].append(row)
        for prod, group in by_product.items():
            result.append(_rollup(group, product=prod, provider=None, model=None))
        for (provider, model), group in by_model.items():
            result.append(_rollup(group, product=None, provider=provider, model=model))
        return result

    def list_events(
        self,
        *,
        tenant_id: int,
        patient_id: str,
        start: datetime,
        end: datetime,
        product: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[UsageEventOut]]:
        rows = self._filtered(tenant_id, patient_id, start, end, product)
        rows.sort(key=lambda r: r["occurred_at"], reverse=True)
        page = rows[offset: offset + limit]
        events = [
            UsageEventOut(
                request_id=r["request_id"] if isinstance(r["request_id"], UUID) else UUID(str(r["request_id"])),
                occurred_at=_aware(r["occurred_at"]),
                product=r["product"],
                feature=r.get("feature") or "",
                provider=r["provider"],
                model=r["model"],
                prompt_tokens=int(r["prompt_tokens"]),
                completion_tokens=int(r["completion_tokens"]),
                total_tokens=int(r["total_tokens"]),
                cost_usd=money(r["cost_usd"]),
                pricing_status=r["pricing_status"],
                job_id=r.get("job_id"),
                source_service=r.get("source_service"),
            )
            for r in page
        ]
        return len(rows), events

    def _filtered(
        self,
        tenant_id: int,
        patient_id: str,
        start: datetime,
        end: datetime,
        product: Optional[str],
    ) -> list[dict[str, Any]]:
        start = _aware(start)
        end = _aware(end)
        out = []
        for row in self.events.values():
            if int(row["tenant_id"]) != int(tenant_id):
                continue
            if str(row["patient_id"]) != str(patient_id):
                continue
            when = _aware(row["occurred_at"])
            if when < start or when >= end:
                continue
            if product and row["product"] != product:
                continue
            out.append(row)
        return out


def _rollup(
    rows: list[dict[str, Any]],
    *,
    product: Optional[str],
    provider: Optional[str],
    model: Optional[str],
) -> dict[str, Any]:
    return {
        "product": product,
        "provider": provider,
        "model": model,
        "llm_calls": len(rows),
        "prompt_tokens": sum(int(r["prompt_tokens"]) for r in rows),
        "completion_tokens": sum(int(r["completion_tokens"]) for r in rows),
        "total_tokens": sum(int(r["total_tokens"]) for r in rows),
        "cost_usd": sum(Decimal(str(r["cost_usd"])) for r in rows),
        "unpriced_calls": sum(1 for r in rows if r.get("pricing_status") == "unpriced"),
    }


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
