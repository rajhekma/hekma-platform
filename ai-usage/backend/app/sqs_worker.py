from __future__ import annotations

import json
import logging
import threading
import time
from typing import Optional

from .config import Settings
from .ingest_service import IngestService

logger = logging.getLogger(__name__)


class SqsWorker:
    def __init__(self, ingest: IngestService, settings: Settings) -> None:
        self._ingest = ingest
        self._settings = settings
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        import boto3

        self._client = boto3.client(
            "sqs",
            region_name=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url or None,
        )
        self._queue_url = settings.ai_usage_sqs_queue_url or ""

    def start(self) -> None:
        self._queue_url = self._ensure_queue()
        self._thread = threading.Thread(target=self._loop, name="ai-usage-sqs", daemon=True)
        self._thread.start()
        logger.info("SQS worker started queue=%s", self._queue_url)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _ensure_queue(self) -> str:
        if self._settings.ai_usage_sqs_queue_url:
            return self._settings.ai_usage_sqs_queue_url
        name = self._settings.ai_usage_sqs_queue_name
        try:
            return self._client.get_queue_url(QueueName=name)["QueueUrl"]
        except Exception:
            created = self._client.create_queue(QueueName=name)
            logger.info("created SQS queue %s", name)
            return created["QueueUrl"]

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                resp = self._client.receive_message(
                    QueueUrl=self._queue_url,
                    MaxNumberOfMessages=self._settings.sqs_max_messages,
                    WaitTimeSeconds=self._settings.sqs_wait_seconds,
                    VisibilityTimeout=30,
                )
            except Exception as exc:
                logger.warning("SQS receive failed: %s", exc)
                time.sleep(2)
                continue

            for message in resp.get("Messages") or []:
                if self._stop.is_set():
                    break
                receipt = message["ReceiptHandle"]
                try:
                    body = json.loads(message["Body"])
                    self._ingest.ingest(body)
                    self._client.delete_message(QueueUrl=self._queue_url, ReceiptHandle=receipt)
                except Exception:
                    logger.exception("failed to ingest SQS message id=%s", message.get("MessageId"))
