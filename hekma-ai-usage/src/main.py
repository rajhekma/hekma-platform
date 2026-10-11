from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from api.routes import register_routes
from config import Settings, get_settings
from repository.store import PostgresUsageRepository, UsageRepository, open_repository
from service.ingest import IngestService
from service.sqs_worker import SqsWorker

logger = logging.getLogger("hekma.ai_usage")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app(
    repo: Optional[UsageRepository] = None,
    settings: Optional[Settings] = None,
    start_sqs: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    worker_holder: dict[str, Optional[SqsWorker]] = {"worker": None}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        owned_repo = False
        if getattr(app.state, "repo", None) is None:
            store = open_repository(settings.database_url)
            if hasattr(store, "migrate"):
                store.migrate()
            app.state.repo = store
            owned_repo = True
        app.state.settings = settings
        app.state.ingest = IngestService(app.state.repo)
        if start_sqs and settings.sqs_enabled and isinstance(app.state.repo, PostgresUsageRepository):
            try:
                worker = SqsWorker(app.state.ingest, settings)
                worker.start()
                worker_holder["worker"] = worker
            except Exception:
                logger.exception("SQS worker did not start; HTTP ingest remains available")
        yield
        if worker_holder["worker"]:
            worker_holder["worker"].stop()
        if owned_repo and hasattr(app.state.repo, "close"):
            app.state.repo.close()

    app = FastAPI(
        title="Hekma AI Usage",
        version="1.0.0",
        lifespan=lifespan,
    )
    if repo is not None:
        app.state.repo = repo
        app.state.settings = settings
        app.state.ingest = IngestService(repo)

    register_routes(app)
    return app


app = create_app()
