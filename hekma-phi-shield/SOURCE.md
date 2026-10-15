# Provenance

Copied from `PHI_PII/PHI-PII` into `hekma-platform/hekma-phi-shield` (S6 · PHI Shield).

The source repo under `PHI_PII/` is unchanged. This tree is the platform copy for
deployment alongside `hekma-patient-health` and `hekma-scanner`.

**Excluded from copy:** `.git`, `.venv`, `node_modules`, `.env`, caches.

**Included:** `models/` (~500MB RoBERTa weights) for local run. Do not commit
large weights without Git LFS — see root `.gitignore`.

**Platform role:** de-identification / PII detection (`PRIVACY_SERVICE_URL` in
Patient Health and Scanner).
