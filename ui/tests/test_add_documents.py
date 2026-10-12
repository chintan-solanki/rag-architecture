import json
import time
import unittest
from queue import Empty
from unittest.mock import Mock, patch

from ui.pages.add_documents import (
    IngestionListener,
    _activity_event_html,
    _clear_activity_events,
    _decode_ingestion_payload,
    _prepend_activity_entry,
)
from ui.sse import SSEEvent


class ClosingResponse:
    def __init__(self) -> None:
        self.closed = False
        self.fp = object()

    def __iter__(self):
        while not self.closed:
            time.sleep(0.005)
        self.fp = None
        raise AttributeError("'NoneType' object has no attribute 'peek'")

    def close(self) -> None:
        self.closed = True
        self.fp = None


class ClosingApiClient:
    def __init__(self, response: ClosingResponse) -> None:
        self.response = response

    def open_ingestion_events(self, client_id: str) -> ClosingResponse:
        return self.response


class IngestionListenerTests(unittest.TestCase):
    def test_existing_listener_is_reused_for_same_client(self) -> None:
        listener = Mock(client_id="client-1")
        session_state = {"ingestion_listener": listener}

        with patch("ui.pages.add_documents.st.session_state", session_state):
            from ui.pages.add_documents import ensure_ingestion_listener

            ensure_ingestion_listener(Mock(), "client-1")

        listener.stop.assert_not_called()
        self.assertIs(session_state["ingestion_listener"], listener)

    def test_activity_cards_are_compact_and_escape_event_content(self) -> None:
        rendered = _activity_event_html(
            {
                "status": "failed",
                "stage": "<invalid>",
                "ingestion_id": "ing-1",
                "document_id": "doc-1",
                "error": "<bad input>",
            }
        )

        self.assertIn("padding:.45rem .65rem", rendered)
        self.assertIn("font-size:.8rem", rendered)
        self.assertIn("&lt;invalid&gt;", rendered)
        self.assertIn("&lt;bad input&gt;", rendered)

    def test_activity_entries_are_prepended_newest_first(self) -> None:
        events = [{"stage": "older"}, {"stage": "oldest"}]

        _prepend_activity_entry(events, {"stage": "newest"})

        self.assertEqual(
            [event["stage"] for event in events], ["newest", "older", "oldest"]
        )

    def test_clear_activity_events_removes_existing_entries(self) -> None:
        events = [{"stage": "in-progress"}, {"stage": "completed"}]

        _clear_activity_events(events)

        self.assertEqual(events, [])

    def test_decodes_fastapi_json_encoded_redis_payload(self) -> None:
        payload = {
            "ingestion_id": "ing-1",
            "document_id": "doc-1",
            "status": "in-progress",
            "stage": "document.fetched",
        }
        event = SSEEvent("message", json.dumps(json.dumps(payload)))

        self.assertEqual(_decode_ingestion_payload(event), payload)

    def test_decodes_dict_payload_without_extra_json_layer(self) -> None:
        payload = {
            "ingestion_id": "ing-1",
            "status": "completed",
            "stage": "document.indexed",
        }
        event = SSEEvent("message", json.dumps(payload))

        self.assertEqual(_decode_ingestion_payload(event), payload)

    def test_stopping_listener_during_response_read_does_not_raise(self) -> None:
        response = ClosingResponse()
        listener = IngestionListener(ClosingApiClient(response), "client-1")
        listener.start()

        event_type, _ = listener.events.get(timeout=1)
        self.assertEqual(event_type, "connected")

        listener.stop()

        self.assertFalse(listener._thread.is_alive())
        remaining_events = []
        while True:
            try:
                remaining_events.append(listener.events.get_nowait()[0])
            except Empty:
                break
        self.assertNotIn("error", remaining_events)


if __name__ == "__main__":
    unittest.main()
