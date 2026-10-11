import logging
import os

logger = logging.getLogger("fasten_ehr")

try:
    from standardwebhooks.webhooks import Webhook, WebhookVerificationError
except ImportError:  # pragma: no cover
    Webhook = None
    WebhookVerificationError = Exception


class FastenWebhookVerificationError(Exception):
    pass


def is_server_webhook_event(event_type: str | None) -> bool:
    """True for Fasten server POSTs (signed); False for frontend widget.complete relay."""
    if not event_type:
        return False
    return event_type.startswith("patient.") or event_type == "webhook.test"


def verify_fasten_webhook(raw_body: bytes, headers: dict) -> None:
    """
    Verify Standard-Webhooks signature when FASTEN_WEBHOOK_SECRET is configured.
    Skips verification when the secret is unset (local/dev without portal config).
    """
    secret = os.getenv("FASTEN_WEBHOOK_SECRET", "").strip()
    env = os.getenv("HEKMA_ENV", "local").strip().lower()
    if not secret:
        if env == "local":
            logger.warning(
                "FASTEN_WEBHOOK_SECRET not set — skipping verify only because HEKMA_ENV=local"
            )
            return
        raise FastenWebhookVerificationError(
            "FASTEN_WEBHOOK_SECRET is required outside local development."
        )

    if Webhook is None:
        raise FastenWebhookVerificationError(
            "standardwebhooks package is not installed; cannot verify webhook signatures"
        )

    normalized_headers = {k.lower(): v for k, v in headers.items()}
    wh = Webhook(secret)
    try:
        wh.verify(raw_body, normalized_headers)
    except WebhookVerificationError as exc:
        raise FastenWebhookVerificationError(str(exc)) from exc
