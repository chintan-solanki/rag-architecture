from __future__ import annotations

from typing import Any

DEFAULT_RETRIEVAL_TYPE = "hybrid"
DEFAULT_TOP_K = 3
RETRIEVAL_TYPES = ("hybrid", "dense", "bm25")
DEFAULT_CANDIDATE_POOL_SIZE = 10
DEFAULT_RETRIEVAL_ALPHA = 0.5
DEFAULT_RERANKER_SCORE_THRESHOLD = 0.5
DEFAULT_GENERATION_CONFIG = {
    "temperature": 0.1,
    "max_output_tokens": 512,
    "top_p": 1.0,
}


def initialize_state(session_state: Any) -> None:
    retrieval_type = session_state.get(
        "retrieval_type", session_state.get("search_type", DEFAULT_RETRIEVAL_TYPE)
    )
    defaults = {
        "client_id": None,
        "active_page": "Add Documents",
        "retrieval_type": retrieval_type,
        "use_reranker": True,
        "top_k": DEFAULT_TOP_K,
        "candidate_pool_size": DEFAULT_CANDIDATE_POOL_SIZE,
        "reranker_score_threshold": DEFAULT_RERANKER_SCORE_THRESHOLD,
        "retrieval_alpha": DEFAULT_RETRIEVAL_ALPHA,
        "generation_temperature": DEFAULT_GENERATION_CONFIG["temperature"],
        "generation_top_p": DEFAULT_GENERATION_CONFIG["top_p"],
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
