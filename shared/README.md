# Shared libraries

Place cross-service packages here during Phase 2.

The AI usage emitter is `hekma_ai_usage/`. Product repos keep a vendored copy of `client.py`.

- `hekma-auth-python/` — JWT validation for FastAPI services
- `hekma-auth-java/` — JWT validation for Spring services

Each library should be published as a small internal package or git submodule consumed by microservice repos.
