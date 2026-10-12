from __future__ import annotations

import html
import http.client
import queue
import threading
from typing import Any
from urllib.parse import urlsplit

import streamlit as st

from ui.api_client import ApiError, RagApiClient
from ui.sse import SSEDecodeError, SSEEvent, decode_json_event, iter_sse_events


class IngestionListener:
    def __init__(self, api_client: RagApiClient, client_id: str) -> None:
        self.api_client = api_client
        self.client_id = client_id
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.stop_event = threading.Event()
        self._response_lock = threading.Lock()
        self._response = None
        self._thread = threading.Thread(
            target=self._run, name="rag-ingestion-events", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        with self._response_lock:
            response = self._response
        if response is not None:
            response.close()
        if self._thread.is_alive():
            self._thread.join(timeout=1)

    def _run(self) -> None:
        delay = 1.0
        while not self.stop_event.is_set():
            response = None
            try:
                response = self.api_client.open_ingestion_events(self.client_id)
                with self._response_lock:
                    self._response = response
                self.events.put(("connected", None))
                for event in iter_sse_events(response):
                    if self.stop_event.is_set():
                        break
                    try:
                        payload = _decode_ingestion_payload(event)
                        self.events.put(("event", _validate_ingestion_event(payload)))
                        delay = 1.0
                    except (SSEDecodeError, ValueError) as exc:
                        self.events.put(("error", str(exc)))
            except (
                ApiError,
                http.client.HTTPException,
                OSError,
                TimeoutError,
                UnicodeDecodeError,
            ) as exc:
                if not self.stop_event.is_set():
                    self.events.put(("error", str(exc)))
            except AttributeError as exc:
                response_closed = response is not None and response.fp is None
                if not (self.stop_event.is_set() and response_closed):
                    self.events.put(("error", str(exc)))
            finally:
                if response is not None:
                    response.close()
                with self._response_lock:
                    self._response = None

            if not self.stop_event.is_set():
                self.events.put(("reconnecting", None))
                if self.stop_event.wait(delay):
                    break
                delay = min(delay * 2, 10.0)


def _decode_ingestion_payload(event: SSEEvent) -> Any:
    payload = decode_json_event(event)
    if isinstance(payload, str):
        payload = decode_json_event(SSEEvent(event.event, payload))
    return payload


def _validate_ingestion_event(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("An ingestion event was not a JSON object.")
    for key in ("ingestion_id", "status", "stage"):
        if not isinstance(payload.get(key), str):
            raise ValueError(f"An ingestion event is missing {key}.")
    for key in ("document_id", "client_id", "error"):
        value = payload.get(key)
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Ingestion event field {key} must be text.")
    return payload


def ensure_ingestion_listener(api_client: RagApiClient, client_id: str) -> None:
    listener = st.session_state.get("ingestion_listener")
    if listener is not None and listener.client_id == client_id:
        return
    if listener is not None:
        listener.stop()
    listener = IngestionListener(api_client, client_id)
    listener.start()
    st.session_state.ingestion_listener = listener


def render_add_documents(api_client: RagApiClient, client_id: str) -> None:
    ensure_ingestion_listener(api_client, client_id)

    st.subheader("Document source")
    input_method = st.radio(
        "Document source type",
        ("Upload a PDF", "Provide a PDF URL"),
        horizontal=True,
        key="document_input_method",
        label_visibility="collapsed",
    )
    uploaded_file = None
    url = ""
    if input_method == "Upload a PDF":
        uploaded_file = st.file_uploader("Choose a PDF", type=["pdf"])
    else:
        url = st.text_input(
            "PDF URL", placeholder="https://example.com/document.pdf"
        )

    chunk_header_type, comment = _render_contextual_retrieval_options()
    submitted = st.button(
        "Add PDF", disabled=st.session_state.ingestion_submission_active
    )

    if submitted and input_method == "Upload a PDF":
        _submit_upload(api_client, client_id, uploaded_file, chunk_header_type, comment)
    elif submitted:
        _submit_url(api_client, client_id, url, chunk_header_type, comment)

    activity_title, clear_logs = st.columns(
        [5, 1], vertical_alignment="center"
    )
    with activity_title:
        st.header("Ingestion Activity")
    with clear_logs:
        if st.button(
            "Clear logs",
            key="clear_ingestion_logs",
            use_container_width=True,
        ):
            _clear_activity_events(st.session_state.ingestion_events)
    _render_ingestion_activity()


def _render_contextual_retrieval_options() -> tuple[str, str]:
    st.subheader("Contextual Retrieval")
    chunk_header_type = st.selectbox(
        "Chunk header (for contextual retrieval)",
        options=(
            "contextualized_chunk_summary",
            "file_metadata",
        ),
        format_func=lambda value: {
            "contextualized_chunk_summary": "Contextualized LLM chunk summary",
            "file_metadata": "File metadata",
        }[value],
        key="contextual_retrieval_chunk_header_type",
    )
    comment = st.text_area(
        "Comment (optional)",
        placeholder="Optional document summary added to each chunk",
        key="contextual_retrieval_comment",
    )
    return chunk_header_type, comment


def _submit_upload(
    api_client: RagApiClient,
    client_id: str,
    uploaded_file: Any,
    chunk_header_type: str,
    comment: str,
) -> None:
    if uploaded_file is None:
        st.error("Choose a PDF file before submitting.")
        return

    filename = uploaded_file.name
    content = uploaded_file.getvalue()
    content_type = uploaded_file.type or ""
    if not filename.lower().endswith(".pdf"):
        st.error("The selected file must have a .pdf filename.")
        return
    if content_type and content_type not in {
        "application/pdf",
        "application/octet-stream",
    }:
        st.error("The selected file is not identified as a PDF.")
        return
    if not content.startswith(b"%PDF"):
        st.error("The selected file does not contain a PDF signature.")
        return

    st.session_state.ingestion_submission_active = True
    try:
        with st.spinner("Submitting PDF..."):
            ingestion_id = api_client.submit_upload(
                client_id=client_id,
                filename=filename,
                content=content,
                content_type=content_type or "application/pdf",
                chunk_header_type=chunk_header_type,
                comment=comment,
            )
        _record_submission_accepted(ingestion_id)
    except ApiError as exc:
        st.error(f"Document submission failed: {exc}")
    finally:
        st.session_state.ingestion_submission_active = False


def _submit_url(
    api_client: RagApiClient,
    client_id: str,
    url: str,
    chunk_header_type: str,
    comment: str,
) -> None:
    value = url.strip()
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
    except ValueError:
        st.error("Enter a valid HTTP or HTTPS URL.")
        return
    if parsed.scheme not in {"http", "https"} or not hostname:
        st.error("Enter a valid HTTP or HTTPS URL.")
        return

    st.session_state.ingestion_submission_active = True
    try:
        with st.spinner("Submitting PDF URL..."):
            ingestion_id = api_client.submit_url(
                client_id=client_id,
                url=value,
                chunk_header_type=chunk_header_type,
                comment=comment,
            )
        _record_submission_accepted(ingestion_id)
    except ApiError as exc:
        st.error(f"Document submission failed: {exc}")
    finally:
        st.session_state.ingestion_submission_active = False


def _record_submission_accepted(ingestion_id: str) -> None:
    _prepend_activity_entry(
        st.session_state.ingestion_events,
        {
            "_log_entry_type": "accepted",
            "ingestion_id": ingestion_id,
            "message": "Document accepted for ingestion.",
        },
    )


def _prepend_activity_entry(
    events: list[dict[str, Any]], event: dict[str, Any]
) -> None:
    events.insert(0, event)


def _clear_activity_events(events: list[dict[str, Any]]) -> None:
    events.clear()


@st.fragment(run_every=1)
def _render_ingestion_activity() -> None:
    listener: IngestionListener | None = st.session_state.get("ingestion_listener")
    if listener is None:
        st.info("Ingestion monitoring is not active.")
        return

    while True:
        try:
            item_type, value = listener.events.get_nowait()
        except queue.Empty:
            break
        if item_type == "event":
            _prepend_activity_entry(st.session_state.ingestion_events, value)
            st.session_state.ingestion_stream_error = None
            st.session_state.ingestion_connection_state = "connected"
        elif item_type == "error":
            st.session_state.ingestion_stream_error = value
            st.session_state.ingestion_connection_state = "reconnecting"
        elif item_type == "connected":
            st.session_state.ingestion_stream_error = None
            st.session_state.ingestion_connection_state = "connected"
        elif item_type == "reconnecting":
            st.session_state.ingestion_connection_state = "reconnecting"

    if st.session_state.ingestion_stream_error:
        st.warning(
            "The ingestion event stream is reconnecting: "
            f"{st.session_state.ingestion_stream_error}"
        )
    elif st.session_state.ingestion_connection_state == "reconnecting":
        st.info("The ingestion event stream disconnected; reconnecting…")
    elif listener.stop_event.is_set():
        st.caption("Ingestion monitoring stopped.")
    else:
        st.caption("Listening for ingestion updates.")

    events = st.session_state.ingestion_events
    with st.container(height=420, border=False):
        if not events:
            st.info("No ingestion activity received yet.")
            return
        st.html("".join(_activity_event_html(event) for event in events))


def _activity_event_html(event: dict[str, Any]) -> str:
    card_start = (
        '<div style="margin:0 0 .4rem;padding:.45rem .65rem;'
        'border:1px solid var(--border-color,rgba(128,128,128,.28));'
        'border-radius:.5rem;line-height:1.25">'
    )
    if event.get("_log_entry_type") == "accepted":
        return (
            f"{card_start}<div style=\"color:#188038;font-weight:600\">"
            f"{_escape(event['message'])}</div>"
            '<div style="font-size:.8rem;opacity:.75">'
            f"Ingestion ID: {_escape(event['ingestion_id'])}</div></div>"
        )

    status = event["status"]
    if status == "completed":
        color = "#188038"
    elif status == "failed":
        color = "#b3261e"
    else:
        color = "inherit"
    details = [
        f'<div style="color:{color};font-weight:600">'
        f"{_escape(status)} · {_escape(event['stage'])}</div>"
    ]
    document_name = event.get("file_name") or event.get("document_id")
    if document_name:
        details.append(
            '<div style="font-size:.8rem;opacity:.75">'
            f"Document: {_escape(document_name)}</div>"
        )
    details.append(
        '<div style="font-size:.8rem;opacity:.75">'
        f"Ingestion ID: {_escape(event['ingestion_id'])}</div>"
    )
    if status == "failed" and event.get("error"):
        details.append(
            '<div style="color:#b3261e;font-size:.85rem">'
            f"{_escape(event['error'])}</div>"
        )
    return f"{card_start}{''.join(details)}</div>"


def _escape(value: str) -> str:
    return html.escape(value)
