"""Unit tests for RAG embedding input truncation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.rag_retrieval_service import truncate_text_for_embedding


class TruncateEmbeddingInputTests(unittest.TestCase):
    def test_empty_text(self):
        self.assertEqual(truncate_text_for_embedding(""), "")
        self.assertEqual(truncate_text_for_embedding("   "), "")

    def test_short_text_unchanged(self):
        text = "Age: 45 years. Diabetes mellitus type 2."
        self.assertEqual(truncate_text_for_embedding(text), text)

    def test_long_text_truncated_under_limit(self):
        text = "word " * 20000
        out = truncate_text_for_embedding(text, max_tokens=100)
        self.assertLess(len(out), len(text))
        self.assertTrue(out.startswith("word"))

    @patch("services.rag_retrieval_service._get_tiktoken_encoding")
    @patch("services.rag_retrieval_service._get_openai_client")
    def test_embed_uses_truncated_text(self, mock_get_client, mock_get_enc):
        from services import rag_retrieval_service

        enc = MagicMock()
        enc.encode.side_effect = lambda s: list(range(len(s) // 5 + 1))
        enc.decode.side_effect = lambda tokens: "x" * len(tokens)
        mock_get_enc.return_value = enc

        client = MagicMock()
        mock_get_client.return_value = client
        client.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1, 0.2])]
        )

        rag_retrieval_service._embed("clinical note " * 5000)

        sent = client.embeddings.create.call_args.kwargs["input"]
        self.assertLessEqual(len(enc.encode(sent)), rag_retrieval_service._embed_max_tokens())


if __name__ == "__main__":
    unittest.main()
