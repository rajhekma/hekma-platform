"""SQLite store for running commerce without Docker/Postgres."""

from __future__ import annotations

import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from .pricing import ModelPrice
from .repository import _aware, _rollup
from .schemas import UsageEventOut, money

SEED_PRICES = [
    ("openai", "gpt-4o", "2.5", "10", "2024-08-01T00:00:00+00:00"),
    ("openai", "gpt-4o-mini", "0.15", "0.6", "2024-07-18T00:00:00+00:00"),
    ("openai", "gpt-4.1", "2", "8", "2025-04-14T00:00:00+00:00"),
    ("openai", "gpt-4.1-mini", "0.4", "1.6", "2025-04-14T00:00:00+00:00"),
    ("openai", "gpt-4.1-nano", "0.1", "0.4", "2025-04-14T00:00:00+00:00"),
    ("anthropic", "claude-sonnet-4-6", "3", "15", "2025-11-01T00:00:00+00:00"),
    ("anthropic", "claude-sonnet-4-5", "3", "15", "2025-09-01T00:00:00+00:00"),
    ("anthropic", "claude-sonnet-4", "3", "15", "2025-05-22T00:00:00+00:00"),
    ("anthropic", "claude-3-5-sonnet", "3", "15", "2024-06-20T00:00:00+00:00"),
    ("anthropic", "claude-3-haiku", "0.25", "1.25", "2024-03-13T00:00:00+00:00"),
    ("google", "gemini-1.5-pro", "1.25", "5", "2024-09-24T00:00:00+00:00"),
    ("google", "gemini-1.5-flash", "0.075", "0.3", "2024-09-24T00:00:00+00:00"),
    ("google", "gemini-2.0-flash", "0.1", "0.4", "2024-12-11T00:00:00+00:00"),
    ("google", "gemini-2.5-pro", "1.25", "10", "2025-03-25T00:00:00+00:00"),
    ("groq", "llama-3.3-70b", "0.59", "0.79", "2024-12-01T00:00:00+00:00"),
    ("groq", "qwen", "0.2", "0.2", "2025-06-01T00:00:00+00:00"),
]


def sqlite_path_from_url(database_url: str) -> str:
    if database_url == ":memory:" or database_url.endswith(":memory:"):
        return ":memory:"
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        rest = database_url[len(prefix):]
        if rest.startswith("/"):
            return "/" + rest.lstrip("/")
        return rest
    return database_url


class SqliteUsageRepository:
    def __init__(self, database_url: str) -> None:
        path = sqlite_path_from_url(database_url)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def ping(self) -> bool:
        with self._lock:
            self._conn.execute("SELECT 1").fetchone()
        return True

    def migrate(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS ai_model_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    input_usd_per_1m TEXT NOT NULL,
                    output_usd_per_1m TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    effective_to TEXT,
                    UNIQUE (provider, model, effective_from)
                );
                CREATE TABLE IF NOT EXISTS ai_usage_events (
                    request_id TEXT PRIMARY KEY,
                    tenant_id INTEGER NOT NULL DEFAULT 1,
                    patient_id TEXT NOT NULL,
                    product TEXT NOT NULL,
                    feature TEXT NOT NULL DEFAULT '',
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL DEFAULT 0,
                    completion_tokens INTEGER NOT NULL DEFAULT 0,
                    total_tokens INTEGER NOT NULL DEFAULT 0,
                    input_cost_usd TEXT NOT NULL DEFAULT '0',
                    output_cost_usd TEXT NOT NULL DEFAULT '0',
                    cost_usd TEXT NOT NULL DEFAULT '0',
                    pricing_status TEXT NOT NULL DEFAULT 'priced',
                    price_version TEXT,
                    cached INTEGER NOT NULL DEFAULT 0,
                    job_id TEXT,
                    source_service TEXT,
                    occurred_at TEXT NOT NULL,
                    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    schema_version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS ai_usage_events_patient_time_idx
                    ON ai_usage_events (tenant_id, patient_id, occurred_at);
                """
            )
            self._conn.executemany(
                """
                INSERT OR IGNORE INTO ai_model_prices
                    (provider, model, input_usd_per_1m, output_usd_per_1m, effective_from)
                VALUES (?, ?, ?, ?, ?)
                """,
                SEED_PRICES,
            )
            self._conn.commit()

    def insert_event(self, row: dict[str, Any]) -> bool:
        payload = (
            str(row["request_id"]),
            int(row["tenant_id"]),
            str(row["patient_id"]),
            row["product"],
            row.get("feature") or "",
            row["provider"],
            row["model"],
            int(row["prompt_tokens"]),
            int(row["completion_tokens"]),
            int(row["total_tokens"]),
            str(row["input_cost_usd"]),
            str(row["output_cost_usd"]),
            str(row["cost_usd"]),
            row["pricing_status"],
            row.get("price_version"),
            1 if row.get("cached") else 0,
            row.get("job_id"),
            row.get("source_service"),
            _iso(row["occurred_at"]),
            int(row.get("schema_version") or 1),
        )
        with self._lock:
            try:
                self._conn.execute(
                    """
                    INSERT INTO ai_usage_events (
                        request_id, tenant_id, patient_id, product, feature,
                        provider, model, prompt_tokens, completion_tokens, total_tokens,
                        input_cost_usd, output_cost_usd, cost_usd, pricing_status,
                        price_version, cached, job_id, source_service, occurred_at,
                        schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def list_prices(self, at: Optional[datetime] = None) -> list[ModelPrice]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT provider, model, input_usd_per_1m, output_usd_per_1m,
                       effective_from, effective_to
                FROM ai_model_prices
                ORDER BY provider, model, effective_from DESC
                """
            ).fetchall()
        return [
            ModelPrice(
                provider=r["provider"],
                model=r["model"],
                input_usd_per_1m=Decimal(str(r["input_usd_per_1m"])),
                output_usd_per_1m=Decimal(str(r["output_usd_per_1m"])),
                effective_from=_parse_dt(r["effective_from"]),
                effective_to=_parse_dt(r["effective_to"]) if r["effective_to"] else None,
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
        rows = self._filtered(tenant_id, patient_id, start, end, product)
        result = [_rollup(rows, product=None, provider=None, model=None)]
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
                request_id=UUID(str(r["request_id"])),
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
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT * FROM ai_usage_events
                WHERE tenant_id = ? AND patient_id = ?
                """,
                (int(tenant_id), str(patient_id)),
            ).fetchall()
        out = []
        for raw in rows:
            row = dict(raw)
            if product and row["product"] != product:
                continue
            when = _parse_dt(row["occurred_at"])
            if when < start or when >= end:
                continue
            row["occurred_at"] = when
            row["tenant_id"] = int(row["tenant_id"])
            out.append(row)
        return out


def _iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    return str(value)


def _parse_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return _aware(value)
    text = str(value).replace("Z", "+00:00")
    return _aware(datetime.fromisoformat(text))
