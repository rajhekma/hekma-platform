# Hekma Trial Matching

**S5 — Trial Matching (TrialGPT).** Copied from `trailgpt` (see [SOURCE.md](SOURCE.md)).

| Item | Detail |
|------|--------|
| Entry | `main.py` (FastAPI) or `docker_entrypoint.py` |
| Default port | `8000` (Docker / uvicorn) |
| Lite UI | `trialgpt_lite/app.py` — port `8050` |
| Upstream docs | [docs/UPSTREAM_README.md](docs/UPSTREAM_README.md), [docs/TRIAL_GPT_EHR_INGEST.md](docs/TRIAL_GPT_EHR_INGEST.md) |

Patient Health notifies this service after Fasten export when
`TRIALGPT_API_BASE_URL` and `TRIALGPT_EHR_INGEST_API_KEY` are set.

## Run (local)

```bash
cd hekma-trial-matching
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000
```

Gateway today may still proxy trial routes to host `:8000` when running the old
path; platform nginx can be updated to `trial-matching:8000` when this service
is in compose.
