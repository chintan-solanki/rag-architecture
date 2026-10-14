from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from llama_index.core.vector_stores.types import VectorStoreQueryMode

from api.src.models.query import RetrievalConfig, RetrievalType
from api.src.services.retrieval import RetrievalService


class FakeRetriever:
    def __init__(self, nodes: list[SimpleNamespace]) -> None:
        self.nodes = nodes
        self.query = None

    def retrieve(self, query: str) -> list[SimpleNamespace]:
        self.query = query
        return self.nodes


class FakeIndex:
    def __init__(self, nodes: list[SimpleNamespace]) -> None:
        self.nodes = nodes
        self.retriever_options: dict[str, object] | None = None
        self.retriever = FakeRetriever(nodes)

    def as_retriever(self, **kwargs: object) -> FakeRetriever:
        self.retriever_options = kwargs
        return self.retriever


class RetrievalServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = {
            "qdrant": {
                "url": "http://qdrant:6333",
                "collection": "documents",
                "fast_embedding_model": "test-embedding",
            },
            "retrieval": {
                "top_k": 5,
                "candidate_pool_size": 10,
                "embedding_model_cache_dir_name": "embeddings",
                "reranker": {"model": "configured-reranker"},
            },
        }
        self.nodes = [
            SimpleNamespace(
                metadata={"document_id": f"doc-{index}"},
                text=f"content-{index}",
            )
            for index in range(1, 13)
        ]
        self.index = FakeIndex(self.nodes)
        self.service = RetrievalService(self.config)
        self.service._index = self.index
        self.reranker = Mock()

        def score_documents(query: str, documents: list[str]) -> list[float]:
            self.assertEqual(query, "query")
            return [float(index) for index, _ in enumerate(documents)]

        self.reranker.rerank.side_effect = score_documents
        self.service._reranker = self.reranker

    def test_dense_without_reranker_retrieves_only_top_k(self) -> None:
        result = self.service.retrieve(
            "query",
            RetrievalConfig(
                retrieval_type=RetrievalType.dense,
                use_reranker=False,
                top_k=3,
                candidate_pool_size=None,
            ),
        )

        self.assertEqual(
            self.index.retriever_options,
            {
                "similarity_top_k": 3,
                "vector_store_query_mode": VectorStoreQueryMode.DEFAULT,
            },
        )
        self.assertEqual(len(result), 3)
        self.reranker.rerank.assert_not_called()

    def test_bm25_without_reranker_retrieves_only_top_k(self) -> None:
        self.service.retrieve(
            "query",
            RetrievalConfig(
                retrieval_type=RetrievalType.bm25,
                use_reranker=False,
                top_k=3,
            ),
        )

        self.assertEqual(
            self.index.retriever_options,
            {
                "similarity_top_k": 3,
                "vector_store_query_mode": VectorStoreQueryMode.SPARSE,
            },
        )

    def test_hybrid_without_reranker_uses_pool_for_branches_then_top_k(self) -> None:
        self.service.retrieve(
            "query",
            RetrievalConfig(
                retrieval_type=RetrievalType.hybrid,
                use_reranker=False,
                top_k=3,
                candidate_pool_size=8,
                alpha=0.25,
            ),
        )

        self.assertEqual(
            self.index.retriever_options,
            {
                "similarity_top_k": 8,
                "vector_store_query_mode": VectorStoreQueryMode.HYBRID,
                "alpha": 0.25,
                "sparse_top_k": 8,
                "hybrid_top_k": 3,
            },
        )
        self.reranker.rerank.assert_not_called()

    def test_reranker_stage_returns_top_k_after_candidate_retrieval(self) -> None:
        result = self.service.retrieve(
            "query",
            RetrievalConfig(
                retrieval_type=RetrievalType.dense,
                use_reranker=True,
                top_k=3,
                candidate_pool_size=8,
            ),
        )

        self.assertEqual(self.index.retriever_options["similarity_top_k"], 8)
        self.reranker.rerank.assert_called_once_with(
            "query", [f"content-{index}" for index in range(1, 9)]
        )
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0].source.document_id, "doc-8")
        self.assertAlmostEqual(
            result[0].source.relevance_score,
            RetrievalService._sigmoid(7.0),
        )

    def test_reranker_filters_by_sigmoid_score_threshold(self) -> None:
        self.reranker.rerank.side_effect = None
        self.reranker.rerank.return_value = [-2.0, 0.0, 1.0, 2.0]

        result = self.service.retrieve(
            "query",
            RetrievalConfig(
                retrieval_type=RetrievalType.dense,
                use_reranker=True,
                top_k=4,
                candidate_pool_size=4,
                reranker_score_threshold=0.5,
            ),
        )

        self.assertEqual(
            [item.source.document_id for item in result],
            ["doc-4", "doc-3", "doc-2"],
        )
        self.assertAlmostEqual(
            result[-1].source.relevance_score,
            RetrievalService._sigmoid(0.0),
        )

    def test_threshold_one_filters_all_finite_scores(self) -> None:
        result = self.service.retrieve(
            "query",
            RetrievalConfig(
                retrieval_type=RetrievalType.dense,
                use_reranker=True,
                top_k=4,
                candidate_pool_size=4,
                reranker_score_threshold=1.0,
            ),
        )

        self.assertEqual(result, [])
        self.reranker.rerank.assert_not_called()

    def test_hybrid_reranker_fuses_candidate_pool_before_final_reranking(self) -> None:
        self.service.retrieve(
            "query",
            RetrievalConfig(
                retrieval_type=RetrievalType.hybrid,
                use_reranker=True,
                top_k=3,
                candidate_pool_size=8,
                alpha=0.6,
            ),
        )

        self.assertEqual(
            self.index.retriever_options,
            {
                "similarity_top_k": 8,
                "vector_store_query_mode": VectorStoreQueryMode.HYBRID,
                "alpha": 0.6,
                "sparse_top_k": 8,
                "hybrid_top_k": 8,
            },
        )
        self.reranker.rerank.assert_called_once()

    def test_hybrid_uses_configured_pool_when_request_field_is_null(self) -> None:
        self.service.retrieve(
            "query",
            RetrievalConfig(
                retrieval_type=RetrievalType.hybrid,
                use_reranker=False,
                top_k=3,
                candidate_pool_size=None,
            ),
        )

        self.assertEqual(self.index.retriever_options["similarity_top_k"], 10)
        self.assertEqual(self.index.retriever_options["sparse_top_k"], 10)
        self.assertEqual(self.index.retriever_options["hybrid_top_k"], 3)

    def test_missing_request_values_use_server_config_defaults(self) -> None:
        result = self.service.retrieve("query", RetrievalConfig())

        self.assertEqual(
            self.index.retriever_options,
            {
                "similarity_top_k": 10,
                "vector_store_query_mode": VectorStoreQueryMode.HYBRID,
                "alpha": 0.5,
                "sparse_top_k": 10,
                "hybrid_top_k": 10,
            },
        )
        self.assertEqual(len(result), 5)

    def test_candidate_pool_smaller_than_top_k_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate pool size"):
            self.service.retrieve(
                "query",
                RetrievalConfig(
                    retrieval_type=RetrievalType.dense,
                    use_reranker=True,
                    top_k=3,
                    candidate_pool_size=2,
                ),
            )

    def test_reranker_is_initialized_lazily_from_configuration(self) -> None:
        self.service._reranker = None
        reranker_instance = Mock()
        reranker_instance.rerank.return_value = [1.0]
        reranker_type = Mock(return_value=reranker_instance)
        with patch(
            "fastembed.rerank.cross_encoder.TextCrossEncoder",
            reranker_type,
        ):
            self.service._rerank_nodes("query", self.nodes[:1], 0.5)

        reranker_type.assert_called_once_with(
            model_name="configured-reranker",
            cache_dir=self.service.embedding_cache_dir,
        )


if __name__ == "__main__":
    unittest.main()
