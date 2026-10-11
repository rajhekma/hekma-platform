from typing import Optional

SUPPORTED_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "application/pdf"}
)


def guess_mime_type_from_url(url: str, response_content_type: Optional[str]) -> str:
    if response_content_type:
        content_type = response_content_type.split(";")[0].strip().lower()
        if content_type in SUPPORTED_MIME_TYPES or content_type == "image/jpg":
            return "image/jpeg" if content_type == "image/jpg" else content_type

    lower_url = url.lower()
    if lower_url.endswith(".pdf"):
        return "application/pdf"
    if lower_url.endswith(".png"):
        return "image/png"
    if lower_url.endswith(".webp"):
        return "image/webp"
    if lower_url.endswith((".jpg", ".jpeg")):
        return "image/jpeg"

    return "image/jpeg"


def guess_mime_type_from_filename(filename: str, content_type: str = "") -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if content_type in SUPPORTED_MIME_TYPES:
        return content_type
    return "image/jpeg"
