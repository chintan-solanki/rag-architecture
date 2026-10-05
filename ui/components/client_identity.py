from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_component = components.declare_component(
    "rag_ui_client_identity",
    path=str(Path(__file__).with_name("client_identity_frontend")),
)


def get_browser_client_id() -> Any:
    return _component(default=None, key="browser-client-id")
