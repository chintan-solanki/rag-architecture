from contextvars import Context
import unittest
from unittest.mock import patch

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from api.src.models.query import QueryRequest
from api.src.routers.query import query_stream
from api.src.telemetry import Telemetry


class StreamingQueryTracingTests(unittest.TestCase):
    def test_stream_span_is_activated_and_detached_per_iterator_step(self) -> None:
        provider = TracerProvider()
        exporter = InMemorySpanExporter()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        test_telemetry = Telemetry(provider.get_tracer("test"))
        span_states: list[tuple[bool, int, str]] = []

        class Service:
            def stream(self, request: QueryRequest):
                for text in test_telemetry.stream(
                    "service.stream", lambda: ("first", "second")
                ):
                    active_span = trace.get_current_span()
                    span_states.append(
                        (
                            active_span.get_span_context().is_valid,
                            active_span.get_span_context().span_id,
                            request.query,
                        )
                    )
                    yield "answer_delta", text

        request = QueryRequest(query="test")

        def capture_streaming_response(content, **kwargs):
            self.assertEqual(kwargs["media_type"], "text/event-stream")
            return content

        with (
            patch("api.src.routers.query.telemetry", test_telemetry),
            patch(
                "api.src.routers.query.StreamingResponse",
                side_effect=capture_streaming_response,
            ),
        ):
            stream = query_stream(request, Service())
            first_context = Context()
            second_context = Context()
            first_event = first_context.run(next, stream)
            second_event = second_context.run(next, stream)

            with self.assertRaises(StopIteration):
                first_context.run(next, stream)

        self.assertIn("data: {\"text\": \"first\"}", first_event)
        self.assertIn("data: {\"text\": \"second\"}", second_event)
        self.assertTrue(all(state[0] for state in span_states))
        self.assertEqual(len({state[1] for state in span_states}), 1)
        self.assertTrue(all(state[2] == "test" for state in span_states))
        self.assertFalse(first_context.run(trace.get_current_span).get_span_context().is_valid)
        self.assertFalse(second_context.run(trace.get_current_span).get_span_context().is_valid)
        finished_spans = exporter.get_finished_spans()
        self.assertEqual(
            [span.name for span in finished_spans],
            ["service.stream", "query.stream"],
        )


if __name__ == "__main__":
    unittest.main()
