import os

os.environ.setdefault("JWT_SECRET", "test_secret_not_b64!")
os.environ.setdefault("JWT_ALGORITHM", "HS512")
os.environ.setdefault("PG_HOST", "localhost")
os.environ.setdefault("PG_PORT", "5433")
os.environ.setdefault("PG_USER", "hekma")
os.environ.setdefault("PG_PASSWORD", "hekma_local_dev")
os.environ.setdefault("PG_DB", "hekma_platform")
os.environ.setdefault("MYSQL_HOST", "localhost")
os.environ.setdefault("MYSQL_PORT", "3307")
os.environ.setdefault("MYSQL_USER", "hekma")
os.environ.setdefault("MYSQL_PASSWORD", "hekma_local_dev")
os.environ.setdefault("MYSQL_DATABASE", "operations_hekma")
