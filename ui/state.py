from __future__ import annotations

from typing import Any

DEFAULT_SEARCH_TYPE = "hybrid"
DEFAULT_TOP_K = 3
SEARCH_TYPES = ("hybrid", "dense", "bm25")


def initialize_state(session_state: Any) -> None:
    defaults = {
        "client_id": None,
        "active_page": "Add Documents",
        "search_type": DEFAULT_SEARCH_TYPE,
        "top_k": DEFAULT_TOP_K,
        "current_question": "",
        "streamed_answer": "",
        "query_result": None,
        "query_error": None,
        "query_active": False,
        "ingestion_events": [],
        "ingestion_listener": None,
        "ingestion_stream_error": None,
        "ingestion_connection_state": "connecting",
        "ingestion_submission_active": False,
    }
    for key, value in defaults.items():
        if key not in session_state:
            session_state[key] = value.copy() if isinstance(value, list) else value
