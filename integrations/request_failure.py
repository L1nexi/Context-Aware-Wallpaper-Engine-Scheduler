from __future__ import annotations

import requests


def request_failure_reason(exc: requests.RequestException) -> str:
    """Classify an HTTP request failure without exposing its URL or parameters."""

    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ProxyError):
        return "proxy_error"
    if isinstance(exc, requests.exceptions.SSLError):
        return "tls_error"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "connection_error"
    return "request_error"
