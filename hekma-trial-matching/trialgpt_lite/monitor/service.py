"""
Registry Monitor Service.
Tracks total active data, daily new trial additions, and protocol updates for RECRUITING studies
from the official ClinicalTrials.gov REST API v2.
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

from trialgpt_lite.client.ctgov_client import ClinicalTrialsGovClient
from trialgpt_lite.monitor.storage import save_snapshot, get_latest_snapshot, get_history

logger = logging.getLogger("trialgpt_lite.monitor")


class RegistryMonitorService:
    """
    Monitors global ClinicalTrials.gov volume and daily deltas for recruiting studies.
    """

    def __init__(self, client: Optional[ClinicalTrialsGovClient] = None):
        self.client = client or ClinicalTrialsGovClient()
        self._cached_metrics: Optional[dict[str, Any]] = None
        self._cache_timestamp: float = 0.0
        self._cache_ttl_seconds: float = 600.0  # 10 minutes cache

    def get_metrics(self, force_refresh: bool = False) -> dict[str, Any]:
        """
        Retrieves live metrics for status=RECRUITING:
        - Total currently recruiting
        - Newly added in past 24h & 7d
        - Updated in past 24h & 7d
        - Sync status & NLM calendar information
        """
        now_ts = time.time()
        if not force_refresh and self._cached_metrics and (now_ts - self._cache_timestamp < self._cache_ttl_seconds):
            logger.info("Serving registry metrics from in-memory cache.")
            return self._cached_metrics

        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        week_ago_str = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        month_ago_str = (now - timedelta(days=30)).strftime("%Y-%m-%d")

        try:
            # 1. Total recruiting
            total_recruiting = self.client.get_recruiting_count()

            # 2. Newly added (First posted on ClinicalTrials.gov)
            new_24h = self.client.get_recruiting_count(
                date_filter_field="StudyFirstPostDate",
                start_date=yesterday_str,
                end_date=today_str,
            )
            new_7d = self.client.get_recruiting_count(
                date_filter_field="StudyFirstPostDate",
                start_date=week_ago_str,
                end_date=today_str,
            )

            # 3. Protocol updates (Last updated on ClinicalTrials.gov)
            updated_24h = self.client.get_recruiting_count(
                date_filter_field="LastUpdatePostDate",
                start_date=yesterday_str,
                end_date=today_str,
            )
            updated_7d = self.client.get_recruiting_count(
                date_filter_field="LastUpdatePostDate",
                start_date=week_ago_str,
                end_date=today_str,
            )

            # 4. Save to persistent SQLite
            snapshot = save_snapshot(
                total_recruiting=total_recruiting,
                new_24h=new_24h,
                updated_24h=updated_24h,
                new_7d=new_7d,
                updated_7d=updated_7d,
            )

            metrics = {
                "status": "online",
                "total_recruiting": total_recruiting,
                "newly_added": {
                    "last_24h": new_24h,
                    "last_7d": new_7d,
                    "daily_average_7d": round(new_7d / 7.0, 1),
                },
                "updated_studies": {
                    "last_24h": updated_24h,
                    "last_7d": updated_7d,
                    "daily_average_7d": round(updated_7d / 7.0, 1),
                },
                "dates": {
                    "today": today_str,
                    "yesterday": yesterday_str,
                    "week_ago": week_ago_str,
                    "month_ago": month_ago_str,
                },
                "nlm_schedule_note": "NLM/NIH updates the public registry on US business days (Mon–Fri at ~9:00 PM EST). Weekend numbers reflect the latest Friday batch.",
                "last_synced_at": snapshot["recorded_at"],
            }

            self._cached_metrics = metrics
            self._cache_timestamp = now_ts
            return metrics

        except Exception as e:
            logger.error(f"Failed to fetch live registry metrics: {e}")
            # Fallback to latest stored SQLite snapshot
            latest = get_latest_snapshot()
            if latest:
                return {
                    "status": "cached_fallback",
                    "total_recruiting": latest["total_recruiting"],
                    "newly_added": {
                        "last_24h": latest["new_24h"],
                        "last_7d": latest["new_7d"],
                        "daily_average_7d": round(latest["new_7d"] / 7.0, 1),
                    },
                    "updated_studies": {
                        "last_24h": latest["updated_24h"],
                        "last_7d": latest["updated_7d"],
                        "daily_average_7d": round(latest["updated_7d"] / 7.0, 1),
                    },
                    "dates": {"today": today_str},
                    "nlm_schedule_note": "Displaying cached snapshot due to network latency.",
                    "last_synced_at": latest["recorded_at"],
                }
            raise

    def get_feed(self, feed_type: str = "new", days: int = 1, limit: int = 25) -> list[dict[str, Any]]:
        """
        Fetches an interactive feed of studies:
        - feed_type = 'new' (StudyFirstPostDate)
        - feed_type = 'updated' (LastUpdatePostDate)
        """
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        start_date_str = (now - timedelta(days=max(1, days))).strftime("%Y-%m-%d")

        field = "StudyFirstPostDate" if feed_type == "new" else "LastUpdatePostDate"
        return self.client.fetch_recruiting_feed(
            date_filter_field=field,
            start_date=start_date_str,
            end_date=today_str,
            limit=limit,
        )

    def get_trend_history(self, limit_days: int = 30) -> list[dict[str, Any]]:
        """Returns historical daily snapshots from SQLite."""
        return get_history(limit_days=limit_days)
