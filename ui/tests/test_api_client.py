import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

from ui.api_client import RagApiClient
from ui.pages.ask_questions import _build_query_configs


class FakeResponse:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self.body = body
        self.headers = {"Content-Type": content_type}
        self.closed = False

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        self.closed = True

    def __iter__(self):
        return iter(self.body.splitlines(keepends=True))


class ApiClientTests(unittest.TestCase):
    def test_query_config_builder_includes_visible_and_selected_settings(self) -> None:
        retrieval_config, generation_config = _build_query_configs(
            retrieval_type="hybrid",
            use_reranker=True,
            top_k=4,
            candidate_pool_size=12,
            alpha=0.35,
            max_output_tokens=768,
            temperature=0.1,
            top_p=1.0,
        )

        self.assertEqual(
            retrieval_config,
            {
                "retrieval_type": "hybrid",
                "use_reranker": True,
                "top_k": 4,
                "candidate_pool_size": 12,
                "reranker_score_threshold": 0.5,
                "alpha": 0.35,
            },
        )
        self.assertEqual(
            generation_config,
            {"temperature": 0.1, "max_output_tokens": 768, "top_p": 1.0},
        )

    def test_non_hybrid_query_omits_hidden_retrieval_fields(self) -> None:
        retrieval_config, _ = _build_query_configs(
            retrieval_type="dense",
            use_reranker=False,
            top_k=4,
            candidate_pool_size=None,
            alpha=0.5,
            max_output_tokens=512,
            temperature=0.1,
            top_p=1.0,
        )

        self.assertEqual(
            retrieval_config,
            {
                "retrieval_type": "dense",
                "use_reranker": False,
                "top_k": 4,
                "candidate_pool_size": None,
                "reranker_score_threshold": None,
                "alpha": None,
            },
        )

    @patch("ui.api_client.urllib.request.urlopen")
    def test_url_submission_sends_expected_form_and_client_header(self, urlopen) -> None:
        response = FakeResponse(b'{"ingestion_id":"ing-1"}')
        urlopen.return_value = response
        client = RagApiClient("http://localhost:8000/")

        ingestion_id = client.submit_url(
            client_id="browser-1", url="https://example.com/doc.pdf"
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(ingestion_id, "ing-1")
        self.assertEqual(request.full_url, "http://localhost:8000/api/v1/documents")
        self.assertEqual(request.get_header("X_client_id"), "browser-1")
        self.assertEqual(request.get_header("X-client-id"), "browser-1")
        self.assertEqual(
            parse_qs(request.data.decode()),
            {
                "url": ["https://example.com/doc.pdf"],
                "chunk_header_type": ["contextualized_chunk_summary"],
            },
        )
        self.assertTrue(response.closed)

    @patch("ui.api_client.urllib.request.urlopen")
    def test_upload_sends_pdf_as_multipart_file(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(b'{"ingestion_id":"ing-2"}')
        client = RagApiClient("http://localhost:8000")

        ingestion_id = client.submit_upload(
            client_id="browser-2",
            filename="report.pdf",
            content=b"%PDF-1.7\n",
            content_type="application/pdf",
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(ingestion_id, "ing-2")
        self.assertIn('name="file"; filename="report.pdf"', request.data.decode())
        self.assertIn(
            b'name="chunk_header_type"\r\n\r\ncontextualized_chunk_summary',
            request.data,
        )
        self.assertIn(b"%PDF-1.7", request.data)
        self.assertEqual(request.get_header("X_client_id"), "browser-2")
        self.assertEqual(request.get_header("X-client-id"), "browser-2")
        self.assertTrue(request.get_header("Content-type").startswith("multipart/form-data; boundary="))

    @patch("ui.api_client.urllib.request.urlopen")
    def test_query_stream_sends_search_payload_and_decodes_events(self, urlopen) -> None:
        response = FakeResponse(
            b'event: answer_delta\ndata: {"text":"Hello"}\n\n'
            b'event: completed\ndata: {"answer":[],"sources":[]}\n\n',
            "text/event-stream",
        )
        urlopen.return_value = response
        client = RagApiClient("http://localhost:8000")

        events = list(
            client.iter_query_events(
                client_id="browser-3",
                query="What is RAG?",
                retrieval_config={
                    "retrieval_type": "dense",
                    "use_reranker": False,
                    "top_k": 4,
                    "candidate_pool_size": 12,
                    "alpha": 0.35,
                },
                generation_config={
                    "temperature": 0.4,
                    "max_output_tokens": 384,
                    "top_p": 0.85,
                },
            )
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(
            json.loads(request.data),
            {
                "query": "What is RAG?",
                "retrieval_config": {
                    "retrieval_type": "dense",
                    "use_reranker": False,
                    "top_k": 4,
                    "candidate_pool_size": 12,
                    "alpha": 0.35,
                },
                "generation_config": {
                    "temperature": 0.4,
                    "max_output_tokens": 384,
                    "top_p": 0.85,
                },
            },
        )
        self.assertEqual(request.get_header("X_client_id"), "browser-3")
        self.assertEqual(request.get_header("X-client-id"), "browser-3")
        self.assertEqual([event.event for event in events], ["answer_delta", "completed"])
        self.assertTrue(response.closed)

    @patch("ui.api_client.urllib.request.urlopen")
    def test_ingestion_events_include_client_identity_for_current_api_route(
        self, urlopen
    ) -> None:
        response = FakeResponse(b"", "text/event-stream")
        urlopen.return_value = response
        client = RagApiClient("http://localhost:8000")

        opened = client.open_ingestion_events("browser id")
        request = urlopen.call_args.args[0]

        self.assertEqual(
            request.full_url,
            "http://localhost:8000/api/v1/documents/events?x_client_id=browser+id",
        )
        self.assertEqual(request.get_header("X_client_id"), "browser id")
        self.assertEqual(request.get_header("X-client-id"), "browser id")
        opened.close()


if __name__ == "__main__":
    unittest.main()
