from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.deps import AppDeps
from api.internal import register_internal
from api.public import register_public

logger = logging.getLogger("hekma.ai_usage")


def register_routes(app: FastAPI) -> None:
    deps = AppDeps(app)

    @app.exception_handler(ValueError)
    async def _value_error(_, exc: ValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    register_public(app, deps)
    register_internal(app, deps)

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        response = await call_next(request)
        logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
        return response
