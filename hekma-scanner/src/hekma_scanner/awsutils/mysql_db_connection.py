from mysql.connector import pooling
from contextlib import contextmanager
import os

_mysql_pool = None

def _get_mysql_pool():
    global _mysql_pool
    if _mysql_pool is None:
        _mysql_pool = pooling.MySQLConnectionPool(
            pool_name="hekma_mysql_pool",
            pool_size=int(os.getenv("MYSQL_POOL_SIZE", "3")),
            pool_reset_session=False,
            autocommit=True,
            host=os.getenv("MYSQL_HOST", "localhost"),
            user=os.getenv("MYSQL_USER", "hekma"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", "operations_hekma"),
        )
    return _mysql_pool


def warmup_mysql_pool():
    """Pre-initializes the MySQL connection pool in background on startup."""
    try:
        pool = _get_mysql_pool()
        conn = pool.get_connection()
        conn.close()
    except Exception:
        pass




@contextmanager
def mysql_connection():
    """Yields a pooled MySQL connection and always returns it to the pool."""
    conn = None
    try:
        conn = _get_mysql_pool().get_connection()
        conn.autocommit = True
        yield conn
    finally:
        if conn:
            conn.close()



@contextmanager
def mysql_cursor(dictionary=True):
    conn = None
    cursor = None
    try:
        conn = _get_mysql_pool().get_connection()
        conn.autocommit = True
        cursor = conn.cursor(dictionary=dictionary)
        yield cursor
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()







