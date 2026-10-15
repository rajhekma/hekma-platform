"""
Unit tests for Registry Monitoring storage and service.
"""

import unittest
from trialgpt_lite.monitor.storage import (
    init_db,
    save_snapshot,
    get_latest_snapshot,
    get_history,
)


class TestRegistryMonitoringStorage(unittest.TestCase):

    def setUp(self):
        init_db()

    def test_save_and_retrieve_snapshot(self):
        snap = save_snapshot(
            total_recruiting=64486,
            new_24h=34,
            updated_24h=458,
            new_7d=197,
            updated_7d=2108,
        )
        self.assertEqual(snap["total_recruiting"], 64486)
        self.assertEqual(snap["new_24h"], 34)

        latest = get_latest_snapshot()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["total_recruiting"], 64486)

    def test_get_history(self):
        history = get_history(limit_days=5)
        self.assertIsInstance(history, list)
        self.assertGreater(len(history), 0)


if __name__ == "__main__":
    unittest.main()
