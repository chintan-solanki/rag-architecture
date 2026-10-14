from collections.abc import Iterator
from ..helpers.citationprocessor import CitationProcessor
from ..helpers.citations import answer_parts
from ..models.query import QueryRequest, QueryResponse
from .generation import GenerationService
from .retrieval import RetrievalService
from ..telemetry import telemetry

class QueryService:
    def __init__(self, config, retrieval=None, generation=None):
        self.config = config
        self.retrieval = retrieval or RetrievalService(config)
        self.generation = generation or GenerationService(config)

    def _sources(self, request: QueryRequest):
        results = self.retrieval.retrieve(request.query, request.retrieval_config)
        return [item.source if hasattr(item, "source") else item for item in results]

    def query(self, request: QueryRequest) -> QueryResponse:

        with telemetry.span('query'):

            #retrieve rag sources
            sources = self._sources(request)
            if not sources:
                return QueryResponse()

            # get context from the sources
            context = self.retrieval.context(sources)

            #generate llm response
            raw = self.generation.generate(
                request.query, context, request.generation_config
            )

            #retrieve citations
            with telemetry.span('extract citations') as citation_span:
            
                processor = CitationProcessor()
                processor.add_chunk(raw)
                processor.end_src_stream()

                citation_span.set_attributes({
                    'citations_cnt': len(processor.all_citations)
                })

            return QueryResponse(answer=answer_parts(processor.target_text, processor.all_citations, len(sources)), sources=sources)

    def stream(self, request: QueryRequest) -> Iterator[tuple[str, object]]:
        sources = self._sources(request)
        if not sources:
            yield "completed", QueryResponse()
            return
        processor = CitationProcessor()
        context = self.retrieval.context(sources)
        for chunk in self.generation.stream(
            request.query, context, request.generation_config
        ):
            delta = processor.add_chunk(chunk)
            yield "answer_delta", delta
        processor.end_src_stream()
        yield "completed", QueryResponse(
            answer=answer_parts(processor.target_text, processor.all_citations, len(sources)),
            sources=sources,
        )
