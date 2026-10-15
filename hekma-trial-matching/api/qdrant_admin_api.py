import os

from fastapi import APIRouter, Header, HTTPException

from services.qdrant_auto_ingest_service import get_ingest_status, run_qdrant_ingest

router = APIRouter(prefix="/api/admin/qdrant", tags=["Qdrant Admin"])


def _verify_ingest_secret(secret: str | None) -> None:
    expected = (os.getenv("QDRANT_INGEST_ADMIN_SECRET") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="QDRANT_INGEST_ADMIN_SECRET is not configured",
        )
    if secret != expected:
        raise HTTPException(status_code=403, detail="Invalid ingest secret")


@router.get("/status")
def qdrant_ingest_status(
    x_qdrant_ingest_secret: str | None = Header(default=None),
):
    _verify_ingest_secret(x_qdrant_ingest_secret)
    return get_ingest_status()


@router.post("/ingest")
def trigger_qdrant_ingest(
    force: bool = False,
    x_qdrant_ingest_secret: str | None = Header(default=None),
):
    """Trigger patient + trial ingest without shell access."""
    _verify_ingest_secret(x_qdrant_ingest_secret)
    return run_qdrant_ingest(force=force)
