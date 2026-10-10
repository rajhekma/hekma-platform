# AI Usage API

Ingest, pricing, and patient cost queries.

```bash
# From hekma-platform
./scripts/local-dev.sh up
# → http://127.0.0.1:8090/health
```

Without Docker, usage is stored in `data/commerce.db`.

```bash
pytest
```

The emitter other services copy is `hekma_ai_usage/`. Keep the copies in the data pipeline and TrialGPT in sync with it.

See [docs/AI_COST_ANALYTICS.md](../docs/AI_COST_ANALYTICS.md).
