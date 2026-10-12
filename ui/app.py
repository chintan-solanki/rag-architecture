from __future__ import annotations

from pathlib import Path

import streamlit as st

from ui.api_client import RagApiClient
from ui.components.client_identity import get_browser_client_id
from ui.config import ConfigurationError, get_api_base_url
from ui.pages.add_documents import render_add_documents
from ui.pages.ask_questions import render_ask_questions
from ui.state import initialize_state


st.set_page_config(page_title="RAG Assistant", layout="wide")
st.logo(
    str(Path(__file__).resolve().parent / "assets" / "rag_assistant.svg"),
    size="large",
)
st.html(
    "<style>"
    "div[data-testid='stMainBlockContainer']{padding-top:1rem!important}"
    "h1{font-size:1.7rem!important;line-height:1.25!important}"
    "h2{font-size:1.4rem!important;line-height:1.3!important}"
    "h3{font-size:1.2rem!important;line-height:1.35!important}"
    "</style>"
)
initialize_state(st.session_state)

page = st.navigation(
    [
        st.Page(
            lambda: render_add_documents(api_client, st.session_state.client_id),
            title="Add Documents",
            url_path="add-documents",
            default=True,
        ),
        st.Page(
            lambda: render_ask_questions(api_client, st.session_state.client_id),
            title="Ask Questions",
            url_path="ask-questions",
        ),
    ],
    position="sidebar",
)

try:
    api_base_url = get_api_base_url()
except ConfigurationError as exc:
    st.error(str(exc))
    st.stop()

identity = get_browser_client_id()
if isinstance(identity, dict):
    client_id = identity.get("client_id")
    if isinstance(client_id, str) and client_id.strip():
        st.session_state.client_id = client_id
    elif identity.get("error"):
        st.error(identity["error"])

if not st.session_state.client_id:
    st.info("Initializing browser identity…")
    st.stop()

api_client = RagApiClient(api_base_url)
st.session_state.active_page = page.title
page.run()
