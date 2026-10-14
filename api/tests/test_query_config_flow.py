import unittest

from api.src.models.query import (
    GenerationConfig,
    QueryRequest,
    RetrievalConfig,
    RetrievalType,
    Source,
)
from api.src.routers.query import _query_span_attributes
from api.src.services.query_service import QueryService


class FakeRetrievalService:
    def __init__(self) -> None:
        self.received_config: RetrievalConfig | None = None

    def retrieve(self, query: str, retrieval_config: RetrievalConfig) -> list[Source]:
        self.received_config = retrieval_config
        return [Source(id=1, text="source text")]

    @staticmethod
    def context(sources: list[Source]) -> str:
        return "source context"


class FakeGenerationService:
    def __init__(self) -> None:
        self.generate_config: GenerationConfig | None = None
        self.stream_config: GenerationConfig | None = None

    def generate(
        self, query: str, context: str, generation_config: GenerationConfig
    ) -> str:
        self.generate_config = generation_config
        return "Generated answer."

    def stream(
        self, query: str, context: str, generation_config: GenerationConfig
    ):
        self.stream_config = generation_config
        yield "Generated answer."


class QueryConfigFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.retrieval_config = RetrievalConfig(
            retrieval_type=RetrievalType.dense,
            use_reranker=False,
            top_k=4,
            candidate_pool_size=12,
            alpha=0.35,
        )
        self.generation_config = GenerationConfig(
            temperature=0.4,
            max_output_tokens=384,
            top_p=0.85,
        )
        self.request = QueryRequest.model_validate(
            {
                "query": "What is RAG?",
                "retrieval_config": self.retrieval_config.model_dump(),
                "generation_config": self.generation_config.model_dump(),
            }
        )
        self.retrieval = FakeRetrievalService()
        self.generation = FakeGenerationService()
        self.service = QueryService(
            config={}, retrieval=self.retrieval, generation=self.generation
        )

    def test_sync_query_passes_both_configs_to_their_services(self) -> None:
        self.service.query(self.request)

        self.assertEqual(self.retrieval.received_config, self.retrieval_config)
        self.assertEqual(self.generation.generate_config, self.generation_config)

    def test_streaming_query_passes_both_configs_to_their_services(self) -> None:
        list(self.service.stream(self.request))

        self.assertEqual(self.retrieval.received_config, self.retrieval_config)
        self.assertEqual(self.generation.stream_config, self.generation_config)

    def test_query_span_attributes_include_both_configs(self) -> None:
        attributes = _query_span_attributes(self.request)

        self.assertEqual(attributes["retrieval.retrieval_type"], "dense")
        self.assertEqual(attributes["retrieval.use_reranker"], False)
        self.assertEqual(attributes["retrieval.top_k"], 4)
        self.assertEqual(attributes["retrieval.candidate_pool_size"], 12)
        self.assertEqual(attributes["retrieval.alpha"], 0.35)
        self.assertEqual(attributes["generation.temperature"], 0.4)
        self.assertEqual(attributes["generation.max_output_tokens"], 384)
        self.assertEqual(attributes["generation.top_p"], 0.85)


if __name__ == "__main__":
    unittest.main()
