from __future__ import annotations

from contextlib import closing
import html
import http.client
from typing import Any

import streamlit as st

from ui.api_client import ApiError, RagApiClient
from ui.components.citations import render_answer_html, source_card_html
from ui.query_response import ResponseValidationError, validate_query_response
from ui.sse import SSEDecodeError, decode_json_event
from ui.state import (
    DEFAULT_GENERATION_CONFIG,
    RETRIEVAL_TYPES,
)


def render_ask_questions(api_client: RagApiClient, client_id: str) -> None:
    st.html(
        "<style>"
        "div.st-key-use_reranker_widget div[data-testid='stCheckbox']>label"
        "{justify-content:center}"
        "</style>"
    )
    st.subheader("Retrieval settings")
    st.session_state.use_reranker_widget = st.session_state.use_reranker
    st.session_state.retrieval_type_widget = st.session_state.retrieval_type
    st.session_state.retrieval_alpha_widget = st.session_state.retrieval_alpha
    st.session_state.candidate_pool_size_widget = st.session_state.candidate_pool_size
    st.session_state.reranker_score_threshold_widget = (
        st.session_state.reranker_score_threshold
    )
    st.session_state.top_k_widget = st.session_state.top_k
    st.session_state.generation_temperature_widget = (
        st.session_state.generation_temperature
    )
    st.session_state.generation_top_p_widget = st.session_state.generation_top_p

    retrieval_column, alpha_column = st.columns(2)
    with retrieval_column:
        retrieval_type = st.selectbox(
            "Retrieval type",
            RETRIEVAL_TYPES,
            key="retrieval_type_widget",
            on_change=_persist_retrieval_type,
        )
    if retrieval_type == "hybrid":
        with alpha_column:
            alpha_slider_column, alpha_description_column = st.columns(
                [0.72, 0.28], vertical_alignment="center"
            )
            with alpha_slider_column:
                alpha = st.slider(
                    "Alpha",
                    min_value=0.0,
                    max_value=1.0,
                    step=0.05,
                    key="retrieval_alpha_widget",
                    on_change=_persist_retrieval_alpha,
                )
            with alpha_description_column:
                st.caption("dense weight, Relative Score Fusion")
    else:
        alpha = st.session_state.retrieval_alpha

    top_k_column, reranker_column, candidate_column = st.columns(
        3, vertical_alignment="center"
    )
    with top_k_column:
        top_k = st.selectbox(
            "Top K",
            range(1, 11),
            key="top_k_widget",
            on_change=_persist_top_k,
        )
    with reranker_column:
        use_reranker = st.checkbox(
            "Use re-ranker",
            key="use_reranker_widget",
            on_change=_persist_use_reranker,
        )
    if use_reranker:
        with candidate_column:
            candidate_pool_size = st.number_input(
                "Candidate pool size",
                min_value=1,
                max_value=100,
                step=1,
                key="candidate_pool_size_widget",
                on_change=_persist_candidate_pool_size,
            )
    else:
        candidate_pool_size = None

    if use_reranker:
        reranker_score_threshold = st.slider(
            "Re-ranker score threshold",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            key="reranker_score_threshold_widget",
            on_change=_persist_reranker_score_threshold,
            help=(
                "Filters candidates using the sigmoid of the re-ranker's raw "
                "score. This is not a probability or confidence estimate. "
                "Increasing the threshold may filter out more sources with "
                "weaker relevance scores. At 1.0, no finite score passes, "
                "so the result may contain no sources."
            ),
        )
    else:
        reranker_score_threshold = st.session_state.reranker_score_threshold

    st.subheader("Generation Config")
    temperature_column, top_p_column = st.columns(2)
    with temperature_column:
        temperature = st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            key="generation_temperature_widget",
            on_change=_persist_generation_temperature,
        )
    with top_p_column:
        top_p = st.slider(
            "Top-p",
            min_value=0.5,
            max_value=1.0,
            step=0.05,
            key="generation_top_p_widget",
            on_change=_persist_generation_top_p,
        )

    st.session_state.use_reranker = use_reranker
    st.session_state.retrieval_type = retrieval_type
    st.session_state.retrieval_alpha = alpha
    if candidate_pool_size is not None:
        st.session_state.candidate_pool_size = candidate_pool_size
    st.session_state.top_k = top_k

    question_column, button_column = st.columns(
        [0.88, 0.12], gap="small", vertical_alignment="bottom"
    )
    with question_column:
        question = st.text_area(
            "Question",
            placeholder="Ask a question!",
            key="question_input",
            label_visibility="collapsed",
            height=64,
        )
    with button_column:
        ask_clicked = st.button(
            "Ask question",
            type="primary",
            disabled=st.session_state.query_active,
            use_container_width=True,
        )
    if ask_clicked:
        if not question.strip():
            st.error("Enter a question before submitting.")
        else:
            retrieval_config, generation_config = _build_query_configs(
                retrieval_type=retrieval_type,
                use_reranker=use_reranker,
                top_k=top_k,
                candidate_pool_size=candidate_pool_size,
                reranker_score_threshold=reranker_score_threshold,
                alpha=alpha,
                temperature=temperature,
                top_p=top_p,
            )
            _run_query(
                api_client,
                client_id=client_id,
                question=question,
                retrieval_config=retrieval_config,
                generation_config=generation_config,
            )
            return

    if st.session_state.query_result is not None or st.session_state.query_error:
        _render_saved_result()


def _persist_use_reranker() -> None:
    st.session_state.use_reranker = st.session_state.use_reranker_widget


def _persist_retrieval_type() -> None:
    st.session_state.retrieval_type = st.session_state.retrieval_type_widget


def _persist_retrieval_alpha() -> None:
    st.session_state.retrieval_alpha = st.session_state.retrieval_alpha_widget


def _persist_candidate_pool_size() -> None:
    st.session_state.candidate_pool_size = (
        st.session_state.candidate_pool_size_widget
    )


def _persist_reranker_score_threshold() -> None:
    st.session_state.reranker_score_threshold = (
        st.session_state.reranker_score_threshold_widget
    )


def _persist_top_k() -> None:
    st.session_state.top_k = st.session_state.top_k_widget


def _persist_generation_temperature() -> None:
    st.session_state.generation_temperature = (
        st.session_state.generation_temperature_widget
    )


def _persist_generation_top_p() -> None:
    st.session_state.generation_top_p = st.session_state.generation_top_p_widget


def _build_query_configs(
    *,
    retrieval_type: str,
    use_reranker: bool,
    top_k: int,
    candidate_pool_size: int | None,
    reranker_score_threshold: float = 0.5,
    alpha: float,
    temperature: float,
    top_p: float,
) -> tuple[
    dict[str, str | int | float | bool | None],
    dict[str, str | int | float | None],
]:
    return (
        {
            "retrieval_type": retrieval_type,
            "use_reranker": use_reranker,
            "top_k": top_k,
            "candidate_pool_size": candidate_pool_size,
            "reranker_score_threshold": (
                reranker_score_threshold if use_reranker else None
            ),
            "alpha": alpha if retrieval_type == "hybrid" else None,
        },
        {
            **DEFAULT_GENERATION_CONFIG,
            "temperature": temperature,
            "top_p": top_p,
        },
    )


def _run_query(
    api_client: RagApiClient,
    *,
    client_id: str,
    question: str,
    retrieval_config: dict[str, str | int | float | bool | None],
    generation_config: dict[str, str | int | float | None],
) -> None:
    st.session_state.current_question = question
    st.session_state.streamed_answer = ""
    st.session_state.query_result = None
    st.session_state.query_error = None
    st.session_state.query_active = True

    answer_placeholder, source_placeholder = _result_columns(question)
    completed = False
    try:
        with st.spinner("Generating answer..."):
            stream = api_client.iter_query_events(
                client_id=client_id,
                query=question,
                retrieval_config=retrieval_config,
                generation_config=generation_config,
            )
            with closing(stream):
                for event in stream:
                    payload = decode_json_event(event)
                    if event.event == "answer_delta":
                        if not isinstance(payload, dict) or not isinstance(
                            payload.get("text"), str
                        ):
                            raise ResponseValidationError(
                                "An answer_delta event must contain text."
                            )
                        st.session_state.streamed_answer += payload["text"]
                        _render_streamed_answer(
                            answer_placeholder, st.session_state.streamed_answer
                        )
                    elif event.event == "completed":
                        st.session_state.query_result = validate_query_response(payload)
                        completed = True
                        break
                    elif event.event == "error":
                        detail = (
                            payload.get("detail")
                            if isinstance(payload, dict)
                            else None
                        )
                        raise ApiError(
                            detail
                            if isinstance(detail, str)
                            else "The query stream failed."
                        )
    except (
        ApiError,
        http.client.HTTPException,
        OSError,
        TimeoutError,
        SSEDecodeError,
        UnicodeDecodeError,
        ResponseValidationError,
    ) as exc:
        st.session_state.query_error = str(exc)
    finally:
        st.session_state.query_active = False

    if not completed and st.session_state.query_error is None:
        st.session_state.query_error = (
            "The answer stream ended before a completed response was received."
        )
    _render_query_output(
        answer_placeholder,
        source_placeholder,
        st.session_state.query_result,
        st.session_state.streamed_answer,
        st.session_state.query_error,
    )


def _result_columns(question: str):
    answer_column, source_column = st.columns([1.15, 0.85], gap="large")
    with answer_column:
        _render_question(question)
        answer_placeholder = st.empty()
    with source_column:
        source_placeholder = st.empty()
    return answer_placeholder, source_placeholder


def _render_saved_result() -> None:
    answer_placeholder, source_placeholder = _result_columns(
        st.session_state.current_question
    )
    _render_query_output(
        answer_placeholder,
        source_placeholder,
        st.session_state.query_result,
        st.session_state.streamed_answer,
        st.session_state.query_error,
    )


def _render_query_output(
    answer_placeholder: Any,
    source_placeholder: Any,
    result: dict[str, Any] | None,
    streamed_answer: str,
    error: str | None,
) -> None:
    if result is None:
        if not streamed_answer and not error:
            answer_placeholder.empty()
            return
        with answer_placeholder.container():
            if streamed_answer:
                st.markdown(streamed_answer)
            if error:
                st.error(f"Could not complete the answer: {error}")
        return

    answer = result["answer"]
    if not any(part["text"] for part in answer):
        answer_placeholder.info("No answer was returned for this question.")
    else:
        answer_placeholder.html(_answer_html(answer, result["sources"]))

    if result["sources"]:
        with source_placeholder.container():
            st.subheader("Sources")
            for source in result["sources"]:
                st.html(source_card_html(source))
    else:
        source_placeholder.empty()


def _render_question(question: str) -> None:
    st.html(
        '<div style="box-sizing:border-box;width:fit-content;max-width:85%;'
        'margin:0 0 1.2rem auto;padding:.7rem 1rem;'
        'border:1px solid var(--border-color, rgba(128,128,128,.28));'
        'border-radius:1rem;'
        'background:var(--secondary-background-color, #f0f2f6);'
        'color:var(--text-color, #31333f);text-align:right;'
        'white-space:pre-wrap;overflow-wrap:anywhere">'
        f"{html.escape(question)}</div>",
    )


def _render_streamed_answer(placeholder: Any, text: str) -> None:
    placeholder.markdown(text if text else " ")


def _answer_html(
    answer: list[dict[str, Any]], sources: list[dict[str, Any]]
) -> str:
    return render_answer_html(answer, sources)
