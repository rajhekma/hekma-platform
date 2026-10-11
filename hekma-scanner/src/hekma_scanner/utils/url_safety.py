"""Block SSRF on caller-supplied download URLs."""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse


class UnsafeDownloadUrlError(ValueError):
    """URL is not allowed for server-side fetch."""


def _blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or str(ip) in {"169.254.169.254", "fd00:ec2::254"}
    )


def assert_safe_download_url(url: str) -> None:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeDownloadUrlError("Only http(s) document URLs are allowed.")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise UnsafeDownloadUrlError("Document URL host is missing.")
    if host in {"localhost", "metadata.google.internal"}:
        raise UnsafeDownloadUrlError("Document URL host is not allowed.")

    allow = {
        h.strip().lower()
        for h in os.getenv("HEKMA_SCAN_URL_HOSTS", "").split(",")
        if h.strip()
    }
    if allow and host not in allow and not any(host.endswith("." + h) for h in allow):
        raise UnsafeDownloadUrlError("Document URL host is not on the allow list.")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeDownloadUrlError("Document URL host could not be resolved.") from exc

    for info in infos:
        raw = info[4][0]
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if _blocked_ip(ip):
            raise UnsafeDownloadUrlError("Document URL resolves to a private address.")
