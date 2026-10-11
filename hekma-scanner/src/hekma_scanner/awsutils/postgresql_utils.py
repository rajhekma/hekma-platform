import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from contextlib import contextmanager
import threading

load_dotenv()

PG_HOST     = os.getenv("PG_HOST")
PG_PORT     = int(os.getenv("PG_PORT", 5432))
PG_DB       = os.getenv("PG_DB")
PG_USER     = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")

PG_POOL_MIN = int(os.getenv("PG_POOL_MIN", 1))
PG_POOL_MAX = int(os.getenv("PG_POOL_MAX", 24))

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
_pool_lock = threading.Lock()


def _init_pool():
    global _pg_pool
    with _pool_lock:
        if _pg_pool is None:
            _pg_pool = pool.ThreadedConnectionPool(
                PG_POOL_MIN,
                PG_POOL_MAX,
                host=PG_HOST,
                port=PG_PORT,
                database=PG_DB,
                user=PG_USER,
                password=PG_PASSWORD,
                connect_timeout=5,
                application_name="api-backend",
            )


def _get_conn():
    if _pg_pool is None:
        _init_pool()

    conn = _pg_pool.getconn()
    conn.autocommit = False

    # Kill runaway queries early (VERY important in prod)
    with conn.cursor() as cur:
        cur.execute(f"SET statement_timeout = {PG_STATEMENT_TIMEOUT_MS}")

    return conn


def _release_conn(conn):
    if _pg_pool and conn:
        _pg_pool.putconn(conn)


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
        conn.rollback()
        raise
    finally:
        if cur:
            cur.close()
        _release_conn(conn)



# Shutdown hook
def close_pg_pool():
    global _pg_pool
    with _pool_lock:
        if _pg_pool:
            _pg_pool.closeall()
            _pg_pool = None
