from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class PrescriptionExtractor(Protocol):
    """Contract for prescription document extraction (DIP)."""

    def extract_from_bytes(self, content: bytes, mime_type: str) -> dict:
        ...

    def extract_from_url(self, source_url: str) -> dict:
        ...
