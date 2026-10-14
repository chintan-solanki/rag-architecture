
from collections.abc import Callable, Generator, Iterable, Iterator
from contextlib import contextmanager
from typing import TypeVar
from opentelemetry import trace
from opentelemetry.trace import Span, Tracer
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

T = TypeVar("T")


def init_telemetry(endpoint="http://jaeger:4317"):
    resource = Resource(attributes={
        "service.name": "ragapi",
        "service.version": "1.0.0"
    })
    
    provider = TracerProvider(resource=resource)
    
    # Configure OTLP exporter to push traces to your Jaeger backend
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)


tracer = trace.get_tracer("ragapi")


class Telemetry:
    def __init__(self, tracer: Tracer):
        self._tracer = tracer

    @staticmethod
    def _set_attributes(span: Span, attributes: dict[str, object]) -> None:
        for key, value in attributes.items():
            if value is not None:
                span.set_attribute(key, value)

    @contextmanager
    def span(self, name: str, **attributes: object) -> Generator[Span, None, None]:
        with self._tracer.start_as_current_span(name) as active:
            self._set_attributes(active, attributes)
            yield active

    def stream(
        self,
        name: str,
        source: Callable[[], Iterable[T]],
        attributes: dict[str, object] | None = None,
    ) -> Iterator[T]:
        span = self._tracer.start_span(name)
        stream_end = object()
        iterator: Iterator[T] | None = None
        try:
            self._set_attributes(span, attributes or {})
            with trace.use_span(span, end_on_exit=False):
                iterator = iter(source())

            while True:
                with trace.use_span(span, end_on_exit=False):
                    item = next(iterator, stream_end)
                if item is stream_end:
                    break
                yield item
        finally:
            try:
                if iterator is not None:
                    close = getattr(iterator, "close", None)
                    if close is not None:
                        close()
            finally:
                span.end()


telemetry = Telemetry(tracer)