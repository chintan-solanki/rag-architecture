import sys
from dataclasses import dataclass
from math import exp
from threading import Lock
from typing import Any
from pathlib import Path
from dotenv import load_dotenv

#load environment variables from .env file
load_dotenv()

#add api directory to sys.path so we can import modules from it
SRC_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = SRC_DIR.parent.parent
MODEL_DIR = ROOT_DIR / '.models' #this is embedding model, not fastapi model

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.vector_stores.types import VectorStoreQueryMode
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.fastembed import FastEmbedEmbedding
import qdrant_client
from ..models.query import RetrievalConfig, RetrievalType, Source
from ..telemetry import trace_span

@dataclass
class Retrieved:
    source: Source
    node: Any = None


@dataclass(frozen=True)
class RetrievalSettings:
    retrieval_type: RetrievalType
    use_reranker: bool
    top_k: int
    candidate_pool_size: int
    alpha: float
    reranker_score_threshold: float
    stage_one_limit: int
    hybrid_output_limit: int
    span_attributes: dict[str, object]


class RetrievalService:
    def __init__(
        self,
        config,
        url: str | None = None,
        collection: str | None = None,
    ):

        self.url = url or config['qdrant']['url']
        self.collection = collection or config['qdrant']['collection']
        self.embedding_model_name = config['qdrant']['fast_embedding_model']

        self.retrieval_defaults = config["retrieval"]
        self._index = None
        self._reranker = None
        self._reranker_lock = Lock()

        SRC_DIR = Path(__file__).resolve().parent.parent
        ROOT_DIR = SRC_DIR.parent.parent
        MODEL_DIR = ROOT_DIR / '.models'

        self.embedding_cache_dir = str(MODEL_DIR / config['retrieval']['embedding_model_cache_dir_name'])

    def _load_index(self):

        if self._index is None:

            print(f'embedding cache dir is.. {self.embedding_cache_dir}')

            #initialize local embedding model
            local_embed = FastEmbedEmbedding(model_name=self.embedding_model_name, cache_dir=self.embedding_cache_dir)
            Settings.embed_model = local_embed

            print('loading index..', self.collection, self.url)
            client = qdrant_client.QdrantClient(url=self.url)
            print('client initialized..')
            store = QdrantVectorStore(
                client=client, 
                collection_name=self.collection, 
                enable_hybrid=True,
                fastembed_sparse_model="Qdrant/bm25"
            )

            print('vectorstore initialized..')
            self._index = VectorStoreIndex.from_vector_store(store)
            print('index initialized')
        return self._index

    @staticmethod
    def source_from_node(
        node: Any,
        local_id: int,
        relevance_score: float | None = None,
    ) -> Source:
        metadata = dict(getattr(node, "metadata", {}) or {})
        text = getattr(node, "text", None) or getattr(node, "get_content", lambda: "")()
        def value(*names):
            return next((metadata[n] for n in names if metadata.get(n) is not None), None)
        return Source(
            id=local_id, text=text or "", relevance_score=relevance_score,
            chunk_id=value("chunk_id"),
            document_id=value("document_id", "doc_id"),
            section_title=value("section_title", "section"),
            file_name=value("file_name", "filename"),
            original_file_name=value("original_file_name"),
            file_title=value("file_title", "title", "document_title"),
            file_author=value("file_author", "author"),
            chunk_start_page_idx=value("chunk_start_page_idx", "start_page_idx"),
            chunk_end_page_idx=value("chunk_end_page_idx", "end_page_idx"),
        )

    def retrieve(
        self,
        query: str,
        retrieval_config: RetrievalConfig | None = None,
    ) -> list[Retrieved]:
        settings = self._resolve_settings(retrieval_config or RetrievalConfig())
        with trace_span("retrieve", **settings.span_attributes):
            retriever_options: dict[str, Any] = {
                "similarity_top_k": settings.stage_one_limit
            }
            if settings.retrieval_type == RetrievalType.bm25:
                retriever_options["vector_store_query_mode"] = (
                    VectorStoreQueryMode.SPARSE
                )
            elif settings.retrieval_type == RetrievalType.dense:
                retriever_options["vector_store_query_mode"] = (
                    VectorStoreQueryMode.DEFAULT
                )
            else:
                retriever_options.update(
                    vector_store_query_mode=VectorStoreQueryMode.HYBRID,
                    alpha=settings.alpha,
                    sparse_top_k=settings.candidate_pool_size,
                    hybrid_top_k=settings.hybrid_output_limit,
                )

            retriever = self._load_index().as_retriever(**retriever_options)
            nodes = retriever.retrieve(query)
            if settings.use_reranker:
                nodes = nodes[:settings.candidate_pool_size]
                scored_nodes = self._rerank_nodes(
                    query,
                    nodes,
                    settings.reranker_score_threshold,
                )[:settings.top_k]
            else:
                scored_nodes = [
                    (node, None) for node in nodes[:settings.top_k]
                ]
            print(f'retrieved {len(scored_nodes)} source nodes')
            return [
                Retrieved(
                    self.source_from_node(node, i, relevance_score),
                    node,
                )
                for i, (node, relevance_score) in enumerate(scored_nodes, 1)
            ]

    def _resolve_settings(
        self,
        request_config: RetrievalConfig,
    ) -> RetrievalSettings:
        defaults = self.retrieval_defaults
        retrieval_type = request_config.retrieval_type or RetrievalType(
            defaults.get("retrieval_type", RetrievalType.hybrid.value)
        )
        use_reranker = (
            request_config.use_reranker
            if request_config.use_reranker is not None
            else defaults.get("use_reranker", True)
        )
        top_k = (
            request_config.top_k
            if request_config.top_k is not None
            else defaults["top_k"]
        )
        needs_candidate_pool = (
            use_reranker or retrieval_type == RetrievalType.hybrid
        )
        if needs_candidate_pool:
            candidate_pool_size = (
                request_config.candidate_pool_size
                if request_config.candidate_pool_size is not None
                else defaults.get("candidate_pool_size", top_k)
            )
        else:
            candidate_pool_size = top_k
        if candidate_pool_size < top_k:
            raise ValueError(
                "Configured candidate pool size must be greater than or equal to top_k."
            )

        alpha = (
            request_config.alpha
            if request_config.alpha is not None
            else defaults.get("alpha", 0.5)
        )
        reranker_score_threshold = (
            request_config.reranker_score_threshold
            if request_config.reranker_score_threshold is not None
            else defaults.get("reranker_score_threshold", 0.5)
        )
        stage_one_limit = candidate_pool_size if needs_candidate_pool else top_k
        hybrid_output_limit = candidate_pool_size if use_reranker else top_k
        span_attributes: dict[str, object] = {
            "retrieval_type": retrieval_type.value,
            "use_reranker": use_reranker,
            "top_k": top_k,
            "candidate_pool_size": candidate_pool_size if needs_candidate_pool else None,
        }
        if use_reranker:
            span_attributes["reranker_score_threshold"] = (
                reranker_score_threshold
            )
        if retrieval_type == RetrievalType.hybrid:
            span_attributes["alpha"] = alpha

        return RetrievalSettings(
            retrieval_type=retrieval_type,
            use_reranker=use_reranker,
            top_k=top_k,
            candidate_pool_size=candidate_pool_size,
            alpha=alpha,
            reranker_score_threshold=reranker_score_threshold,
            stage_one_limit=stage_one_limit,
            hybrid_output_limit=hybrid_output_limit,
            span_attributes=span_attributes,
        )

    def _rerank_nodes(
        self,
        query: str,
        nodes: list[Any],
        score_threshold: float,
    ) -> list[tuple[Any, float]]:
        if not nodes or score_threshold >= 1.0:
            return []
        if self._reranker is None:
            with self._reranker_lock:
                if self._reranker is None:
                    from fastembed.rerank.cross_encoder import TextCrossEncoder

                    reranker_config = self.retrieval_defaults.get("reranker", {})
                    self._reranker = TextCrossEncoder(
                        model_name=reranker_config.get(
                            "model", "Xenova/ms-marco-MiniLM-L-6-v2"
                        ),
                        cache_dir=self.embedding_cache_dir,
                    )
        documents = [self.source_from_node(node, 1).text for node in nodes]
        scores = list(self._reranker.rerank(query, documents))
        if len(scores) != len(nodes):
            raise RuntimeError(
                "Reranker returned a different number of scores than input nodes."
            )
        scored_nodes = sorted(
            zip(scores, nodes),
            key=lambda scored_node: scored_node[0],
            reverse=True,
        )
        normalized_scored_nodes = [
            (node, self._sigmoid(score)) for score, node in scored_nodes
        ]
        return [
            (node, score)
            for node, score in normalized_scored_nodes
            if score >= score_threshold
        ]

    @staticmethod
    def _sigmoid(score: float) -> float:
        if score >= 0:
            return 1 / (1 + exp(-score))
        exp_score = exp(score)
        return exp_score / (1 + exp_score)

    @staticmethod
    def context(sources: list[Source]) -> str:
        return "\n\n".join(f"Source [{source.id}]\n{source.text}" for source in sources)
