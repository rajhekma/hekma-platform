from __future__ import annotations

import hmac
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
        expected = (cfg.ai_cost_api_key or "").strip()
        env = (cfg.hekma_env or "local").strip().lower()
        if not expected:
            if env == "local":
                return
            raise HTTPException(
                status_code=503,
                detail="AI_COST_API_KEY is required outside local development.",
            )
        provided = (x_api_key or "").strip()
        if not provided or not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

    return _require_key
