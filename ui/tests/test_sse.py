import unittest

from ui.sse import SSEDecodeError, SSEEvent, decode_json_event, iter_sse_events


class SSEParserTests(unittest.TestCase):
    def test_parses_named_events_and_multiline_data(self) -> None:
        lines = [
            b"event: answer_delta\r\n",
            b"data: {\"text\":\r\n",
            b'data: "hello"}\r\n',
            b"\r\n",
            b": heartbeat\n",
            b"data: {\"answer\": []}\n",
            b"\n",
        ]

        self.assertEqual(
            list(iter_sse_events(lines)),
            [
                SSEEvent("answer_delta", '{"text":\n"hello"}'),
                SSEEvent("message", '{"answer": []}'),
            ],
        )

    def test_dispatches_final_event_without_blank_line(self) -> None:
        self.assertEqual(
            list(iter_sse_events(["event: completed\n", 'data: {"answer": []}'])),
            [SSEEvent("completed", '{"answer": []}')],
        )

    def test_decodes_json_and_reports_invalid_json(self) -> None:
        self.assertEqual(decode_json_event(SSEEvent("answer_delta", '{"text":"x"}')), {"text": "x"})
        with self.assertRaises(SSEDecodeError):
            decode_json_event(SSEEvent("completed", "not-json"))


if __name__ == "__main__":
    unittest.main()
