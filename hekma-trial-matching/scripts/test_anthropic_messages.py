"""Anthropic Messages.create must work when the SDK rejects temperature."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.anthropic_messages import create_anthropic_message


class AnthropicTemperatureCompatTests(unittest.TestCase):
    def test_strips_temperature_before_create(self):
        client = MagicMock()
        client.messages.create.return_value = MagicMock(content=[])
        create_anthropic_message(
            client,
            model="claude-sonnet-4-6",
            max_tokens=1024,
            temperature=0,
            messages=[],
        )
        self.assertEqual(client.messages.create.call_count, 1)
        self.assertNotIn("temperature", client.messages.create.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
