from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit


class ConfigurationError(ValueError):
    pass


def get_api_base_url() -> str:
    configured_url = os.environ.get("RAG_API_BASE_URL", "").strip()
    if not configured_url:
        raise ConfigurationError(
            "RAG_API_BASE_URL is not configured. Set it to the reachable RAG API URL."
        )

    try:
        parsed = urlsplit(configured_url)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as exc:
        raise ConfigurationError(
            "RAG_API_BASE_URL must be a valid absolute HTTP or HTTPS URL."
        ) from exc
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not hostname:
        raise ConfigurationError(
            "RAG_API_BASE_URL must be an absolute HTTP or HTTPS URL."
        )
    if parsed.query or parsed.fragment:
        raise ConfigurationError(
            "RAG_API_BASE_URL must not include a query string or fragment."
        )

    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "")
    )
