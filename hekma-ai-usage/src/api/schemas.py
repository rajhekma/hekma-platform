from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str = "ai-usage"
    database: str = "unknown"
    sqs: str = "disabled"
