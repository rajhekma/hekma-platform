# Hekma PHI Shield

**S6 — Privacy / PHI de-identification.** Copied from `PHI-PII` (see [SOURCE.md](SOURCE.md)).

| Item | Detail |
|------|--------|
| Entry | `api/main.py` or `python run_local.py` |
| Default port | `8080` (`SERVICE_PORT`) |
| API docs | `http://localhost:8080/docs` |
| Upstream docs | [docs/UPSTREAM_README.md](docs/UPSTREAM_README.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DEVOPS_DEPLOYMENT_GUIDE.md](DEVOPS_DEPLOYMENT_GUIDE.md) |

Patient Health and Scanner call this service when `PRIVACY_SERVICE_ENABLED=true`
and `PRIVACY_SERVICE_URL` points here.

## Run (local)

```bash
cd hekma-phi-shield
cp .env.example .env
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python api/main.py
```

Not yet wired in `docker-compose.yml` or `api-gateway/nginx.conf` — add when
cutting over from a standalone PHI deploy.
