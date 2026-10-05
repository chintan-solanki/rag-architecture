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
from ui.state import SEARCH_TYPES


def render_ask_questions(api_client: RagApiClient, client_id: str) -> None:
    st.subheader("Search Settings")
    settings_left, settings_right = st.columns(2)
    st.session_state.search_type_widget = st.session_state.search_type
    st.session_state.top_k_widget = st.session_state.top_k
    with settings_left:
        search_type = st.selectbox(
            "Search type",
            SEARCH_TYPES,
            key="search_type_widget",
            on_change=_persist_search_type,
        )
    with settings_right:
        top_k = st.selectbox(
            "Top K",
            range(1, 6),
            key="top_k_widget",
            on_change=_persist_top_k,
        )
    st.session_state.search_type = search_type
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
            _run_query(
                api_client,
                client_id=client_id,
                question=question,
                search_type=search_type,
                top_k=top_k,
            )
            return

    if st.session_state.query_result is not None or st.session_state.query_error:
        _render_saved_result()


def _persist_search_type() -> None:
    st.session_state.search_type = st.session_state.search_type_widget


def _persist_top_k() -> None:
    st.session_state.top_k = st.session_state.top_k_widget


def _run_query(
    api_client: RagApiClient,
    *,
    client_id: str,
    question: str,
    search_type: str,
    top_k: int,
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
                search_type=search_type,
                top_k=top_k,
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
        answer_placeholder.markdown(
            _answer_html(answer, result["sources"]),
            unsafe_allow_html=True,
        )

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
