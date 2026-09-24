from collections.abc import Iterator
from ..helpers.citationprocessor import CitationProcessor
from ..helpers.citations import answer_parts
from ..models.query import QueryRequest, QueryResponse
from .generation import GenerationService
from .retrieval import RetrievalService


class QueryService:
    def __init__(self, config, retrieval=None, generation=None):
        self.config = config
        self.retrieval = retrieval or RetrievalService(config)
        self.generation = generation or GenerationService(config)

    def _sources(self, request: QueryRequest):
        results = self.retrieval.retrieve(request.query, request.search_type, request.search.top_k)
        return [item.source if hasattr(item, "source") else item for item in results]

    def query(self, request: QueryRequest) -> QueryResponse:
        print(f'query recceived.. {request}')
        sources = self._sources(request)
        if not sources:
            return QueryResponse()
        context = self.retrieval.context(sources)
        raw = self.generation.generate(request.query, context)
        processor = CitationProcessor()
        _, ranges = processor.add_chunk(raw)
        processor.end_src_stream()
        return QueryResponse(answer=answer_parts(processor.target_text, ranges, len(sources)), sources=sources)

    def stream(self, request: QueryRequest) -> Iterator[tuple[str, object]]:
        sources = self._sources(request)
        if not sources:
            yield "completed", QueryResponse()
            return
        processor = CitationProcessor()
        context = self.retrieval.context(sources)
        for chunk in self.generation.stream(request.query, context):
            delta, _ = processor.add_chunk(chunk)
            yield "answer_delta", delta
        processor.end_src_stream()
        yield "completed", QueryResponse(
            answer=answer_parts(processor.target_text, processor.all_citations, len(sources)),
            sources=sources,
        )
