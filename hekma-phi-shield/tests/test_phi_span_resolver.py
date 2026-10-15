"""Unit tests for PHI span alignment."""

from api.services.phi.span_resolver import SpanResolver


def test_resolve_exact_match():
    """Exact substring returns correct offsets."""
    resolver = SpanResolver()
    text = "Patient Jane Doe has diabetes."
    assert resolver.resolve(text, "Jane Doe") == (8, 16)


def test_resolve_uses_hint_when_valid():
    """Hinted start wins when the slice matches."""
    resolver = SpanResolver()
    text = "MRN 111 and MRN 222"
    assert resolver.resolve(text, "MRN 222", hinted_start=12) == (12, 19)


def test_resolve_all_avoids_duplicate_spans():
    """Repeated mentions get distinct unused spans."""
    resolver = SpanResolver()
    text = "aspirin then aspirin again"
    resolved = resolver.resolve_all(
        text,
        [("aspirin", None), ("aspirin", None)],
    )
    assert resolved == [("aspirin", 0, 7), ("aspirin", 13, 20)]


def test_resolve_missing_returns_none():
    """Unknown mention yields None."""
    resolver = SpanResolver()
    assert resolver.resolve("hello", "missing") is None
