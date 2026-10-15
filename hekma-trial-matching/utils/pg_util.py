import logging
import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from contextlib import contextmanager
import threading

load_dotenv()

logger = logging.getLogger(__name__)

PG_HOST     = os.getenv("PG_HOST")
PG_PORT     = int(os.getenv("PG_PORT", 5432))
PG_DB       = os.getenv("PG_DB")
PG_USER     = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")

PG_POOL_MIN = int(os.getenv("PG_POOL_MIN", 1))
PG_POOL_MAX = int(os.getenv("PG_POOL_MAX", 10))

# Optional performance tuning
PG_STATEMENT_TIMEOUT_MS = int(os.getenv("PG_STATEMENT_TIMEOUT_MS", 5000))

# print("PG_HOST:", PG_HOST)
# print("PG_DB:", PG_DB)
# print("PG_USER:", PG_USER)
# print("PG_PASSWORD:", repr(PG_PASSWORD))


if not all([PG_HOST, PG_DB, PG_USER, PG_PASSWORD]):
    raise RuntimeError("PostgreSQL environment variables are not fully set")

# Pool (singleton, thread-safe)
_pg_pool = None
_corpus_pool = None
_pool_lock = threading.Lock()


def _corpus_dsn() -> dict:
    """Connection for public.trialgpt_corpus. Other tables stay on PG_*."""
    host = os.getenv("CORPUS_PG_HOST", "").strip()
    if not host:
        return {
            "host": PG_HOST,
            "port": PG_PORT,
            "database": PG_DB,
            "user": PG_USER,
            "password": PG_PASSWORD,
        }
    database = os.getenv("CORPUS_PG_DB", "").strip()
    user = os.getenv("CORPUS_PG_USER", "").strip()
    password = os.getenv("CORPUS_PG_PASSWORD", "")
    missing = [
        name
        for name, value in {
            "CORPUS_PG_DB": database,
            "CORPUS_PG_USER": user,
            "CORPUS_PG_PASSWORD": password,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError("PostgreSQL corpus environment variables are not fully set: " + ", ".join(missing))
    return {
        "host": host,
        "port": int(os.getenv("CORPUS_PG_PORT", "5432")),
        "database": database,
        "user": user,
        "password": password,
    }


def _make_pool(dsn: dict, application_name: str):
    return pool.SimpleConnectionPool(
        PG_POOL_MIN,
        PG_POOL_MAX,
        connect_timeout=5,
        application_name=application_name,
        **dsn,
    )


def _init_pool():
    global _pg_pool
    with _pool_lock:
        if _pg_pool is None:
            _pg_pool = _make_pool(
                {
                    "host": PG_HOST,
                    "port": PG_PORT,
                    "database": PG_DB,
                    "user": PG_USER,
                    "password": PG_PASSWORD,
                },
                "api-backend",
            )


def _init_corpus_pool():
    global _corpus_pool
    with _pool_lock:
        if _corpus_pool is None:
            dsn = _corpus_dsn()
            _corpus_pool = _make_pool(dsn, "trialgpt-corpus")
            logger.info(
                "trialgpt_corpus db | %s:%s/%s",
                dsn["host"],
                dsn["port"],
                dsn["database"],
            )


def _borrow(target_pool):
    """Return a live pooled connection, replacing ones the server already closed."""
    last_exc = None
    for _ in range(PG_POOL_MAX + 1):
        conn = target_pool.getconn()
        conn.autocommit = False
        try:
            # SET statement_timeout doubles as a connection liveness probe and
            # kills runaway queries early (VERY important in prod).
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {PG_STATEMENT_TIMEOUT_MS}")
            return conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
            last_exc = exc
            try:
                target_pool.putconn(conn, close=True)
            except Exception:
                pass

    raise last_exc if last_exc else psycopg2.OperationalError("Unable to obtain a live connection")


def _get_conn():
    if _pg_pool is None:
        _init_pool()
    return _borrow(_pg_pool)


def _get_corpus_conn():
    if _corpus_pool is None:
        _init_corpus_pool()
    return _borrow(_corpus_pool)


def _release_conn(conn, target_pool=None):
    target = _pg_pool if target_pool is None else target_pool
    if target and conn:
        target.putconn(conn)


# SAFE transaction wrapper
@contextmanager
def pg_transaction(dict_cursor: bool = True):
    """

    - Auto commit on success
    - Auto rollback on exception
    - Always returns connection to pool
    """

    conn = _get_conn()
    cur = None  
    try:
        cursor_factory = RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)
        yield conn, cur
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if cur:
            cur.close()
        _release_conn(conn)


@contextmanager
def pg_corpus_transaction(dict_cursor: bool = True):
    """Read and write public.trialgpt_corpus on CORPUS_PG_*, not the app database."""
    conn = _get_corpus_conn()
    cur = None
    try:
        cursor_factory = RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)
        yield conn, cur
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        if cur:
            cur.close()
        _release_conn(conn, _corpus_pool)



# Shutdown hook
def close_pg_pool():
    global _pg_pool, _corpus_pool
    with _pool_lock:
        if _pg_pool:
            _pg_pool.closeall()
            _pg_pool = None
        if _corpus_pool:
            _corpus_pool.closeall()
            _corpus_pool = None
