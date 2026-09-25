
from contextlib import contextmanager
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

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

@contextmanager
def trace_span(name: str, **attributes):
    try:
        # note that opentelemetry checks the current thread/async context 
        # and automatically handles the nested spans 
        with tracer.start_as_current_span(name) as active:
            for key, value in attributes.items():
                if value is not None:
                    active.set_attribute(key, value)
            yield active
    except ImportError:
        print('error creating trace_span..')
        yield None