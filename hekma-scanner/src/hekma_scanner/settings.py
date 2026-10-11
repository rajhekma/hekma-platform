from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "hekma-scanner"
    service_port: int = 8011
    jwt_secret: str = ""
    jwt_algorithm: str = "HS512"
    jwt_header_prefix: str = "Bearer"

    pg_host: str = "localhost"
    pg_port: int = 5433
    pg_user: str = "hekma"
    pg_password: str = "hekma_local_dev"
    pg_db: str = "hekma_platform"

    mysql_host: str = "localhost"
    mysql_port: int = 3307
    mysql_user: str = "hekma"
    mysql_password: str = "hekma_local_dev"
    mysql_database: str = "operations_hekma"

    redis_host: str = "localhost"
    redis_port: int = 6379

    cache_reprocess_api_key: Optional[str] = None
    statement_timeout_ms: int = 5000
    openai_api_key: Optional[str] = None
    ehr_summary_cache_ttl_hours: int = 24


@lru_cache
def get_settings() -> Settings:
    return Settings()
