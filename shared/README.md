# Shared libraries

Place cross-service packages here during Phase 2.

The AI usage emitter lives with its API at `ai-usage/backend/hekma_ai_usage`.

- `hekma-auth-python/` — JWT validation for FastAPI services
- `hekma-auth-java/` — JWT validation for Spring services

Each library should be published as a small internal package or git submodule consumed by microservice repos.
