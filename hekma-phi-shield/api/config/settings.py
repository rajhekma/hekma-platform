from pathlib import Path
from typing import Set, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Service & Domain Config
    SERVICE_NAME: str = "pii-phi-security-service"
    SERVICE_PORT: int = 8080
    SERVICE_HOST: str = "0.0.0.0"
    CUSTOM_DOMAIN: str = "https://pii-phi.hekma.ai"
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # Storage Backend: "json" | "memory" | "postgresql"
    STORAGE_BACKEND: str = "json"
    DATA_DIR: Path = Path(__file__).parent.parent.parent / "data"
    
    # PostgreSQL Vault Config (Used when STORAGE_BACKEND=postgresql)
    DATABASE_URL: str = ""
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    # Cryptography & Key Management
    ENCRYPTION_KEY: str = ""
    HMAC_SECRET: str = ""
    KMS_ENABLED: bool = False
    AWS_KMS_KEY_ID: str = ""
    AWS_REGION: str = "us-east-1"

    # API Security & Authentication
    SERVICE_API_KEY: str = "dev-internal-key-123"
    ADMIN_API_KEY: str = "admin-dev-key-change-in-production"
    ANONYMIZATION_ENABLED: bool = True
    POLICY_CACHE_TTL: int = 60
    
    EXCLUDED_PATHS: Set[str] = {
        "/",
        "/health",
        "/healthz",
        "/ready",
        "/metrics",
        "/info",
        "/docs",
        "/openapi.json",
        "/entities",
        "/predict",
        "/validate",
        "/mask",
        "/predict/batch",
        "/phi/health",
        "/phi/entities",
        "/phi/predict",
        "/phi/predict/batch",
        "/phi/validate",
        "/phi/mask",
        "/phi/anonymize",
        "/api/v1/anonymize/fhir",
        "/api/v1/anonymize/json",
        "/anonymize",
        "/restore",
    }

    # PHI Clinical Detector: "openai" (current) or "local" (future trained model)
    PHI_DETECTOR_BACKEND: str = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_PHI_MODEL: str = "gpt-4o-mini"
    OPENAI_TIMEOUT_SECONDS: float = 45.0
    PHI_LOCAL_MODEL_PATH: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
