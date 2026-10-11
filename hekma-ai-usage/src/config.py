from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://hekma:hekma_local_dev@localhost:5433/hekma_platform"
    ai_cost_api_key: Optional[str] = None
    hekma_env: str = "local"
    default_tenant_id: int = 1
    aws_region: str = "us-east-1"
    aws_endpoint_url: Optional[str] = None
    ai_usage_sqs_enabled: bool = False
    ai_usage_sqs_queue_name: str = "ai-usage-recorded"
    ai_usage_sqs_queue_url: Optional[str] = None
    sqs_wait_seconds: int = 10
    sqs_max_messages: int = 10

    @property
    def sqs_enabled(self) -> bool:
        return self.ai_usage_sqs_enabled or bool(self.ai_usage_sqs_queue_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
