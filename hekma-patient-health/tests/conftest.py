import os

os.environ.setdefault("JWT_SECRET", "test_secret_not_b64!")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("CACHE_REPROCESS_API_KEY", "test-internal-key")
os.environ.setdefault("PG_HOST", "localhost")
os.environ.setdefault("PG_PORT", "5433")
os.environ.setdefault("PG_USER", "hekma")
os.environ.setdefault("PG_PASSWORD", "hekma_local_dev")
os.environ.setdefault("PG_DB", "hekma_platform")
