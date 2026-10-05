from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True)
class SSEEvent:
    event: str
    data: str


class SSEDecodeError(ValueError):
    pass


def iter_sse_events(lines: Iterable[bytes | str]) -> Iterator[SSEEvent]:
    """Parse the event framing defined by the Server-Sent Events format."""
    event_name = ""
    data_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        line = line.rstrip("\r\n")
        if not line:
            if data_lines:
                yield SSEEvent(event=event_name or "message", data="\n".join(data_lines))
            event_name = ""
            data_lines = []
            continue
        if line.startswith(":"):
            continue

        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)

    if data_lines:
        yield SSEEvent(event=event_name or "message", data="\n".join(data_lines))


def decode_json_event(event: SSEEvent) -> Any:
    try:
        return json.loads(event.data)
    except json.JSONDecodeError as exc:
        raise SSEDecodeError(
            f"The {event.event!r} event contained invalid JSON."
        ) from exc
