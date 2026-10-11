from __future__ import annotations

from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException

from config import Settings
from repository.store import UsageRepository
from service.ingest import IngestService


class AppDeps:
    def __init__(self, app: FastAPI) -> None:
        self.app = app

    def current_repo(self) -> UsageRepository:
        return self.app.state.repo

    def current_ingest(self) -> IngestService:
        return self.app.state.ingest

    def current_settings(self) -> Settings:
        return self.app.state.settings


def require_key(deps: AppDeps):
    def _require_key(
        x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
        cfg: Settings = Depends(deps.current_settings),
    ) -> None:
        if cfg.ai_cost_api_key and x_api_key != cfg.ai_cost_api_key:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return _require_key
