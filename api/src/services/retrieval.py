import os
import sys
from dataclasses import dataclass
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
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.embeddings.fastembed import FastEmbedEmbedding
import qdrant_client
from ..models.query import RetrievalConfig, RetrievalType, Source
from ..telemetry import trace_span

@dataclass
class Retrieved:
    source: Source
    node: Any = None

class RetrievalService:
    def __init__(self, config, url: str | None = None, collection: str | None = None, top_k: int | None = None):

        self.url = url or config['qdrant']['url']
        self.collection = collection or config['qdrant']['collection']
        self.embedding_model_name = config['qdrant']['fast_embedding_model']

        self.top_k = top_k or config['retrieval']['top_k']
        self._index = None

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
    def source_from_node(node: Any, local_id: int) -> Source:
        metadata = dict(getattr(node, "metadata", {}) or {})
        text = getattr(node, "text", None) or getattr(node, "get_content", lambda: "")()
        def value(*names):
            return next((metadata[n] for n in names if metadata.get(n) is not None), None)
        return Source(
            id=local_id, text=text or "", 
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
        retrieval_type = (
            retrieval_config.retrieval_type
            if retrieval_config is not None
            else RetrievalType.hybrid
        )
        top_k = retrieval_config.top_k if retrieval_config is not None else None
        similarity_top_k = top_k if top_k is not None else self.top_k
        span_attributes: dict[str, object] = {
            "retrieval_type": retrieval_type.value,
            "top_k": similarity_top_k,
        }
        if retrieval_config is not None:
            span_attributes.update(
                retrieval_config.model_dump(mode="json", exclude_none=True)
            )

        with trace_span("retrieve", **span_attributes):
            retriever = self._load_index().as_retriever(
                similarity_top_k=similarity_top_k
            )

            # Candidate-pool sizing and alpha remain pass-through configuration for now.
            if retrieval_type == RetrievalType.bm25:
                retriever = self._load_index().as_retriever(
                    similarity_top_k=similarity_top_k,
                    vector_store_query_mode="sparse",
                )
            elif retrieval_type == RetrievalType.dense:
                retriever = self._load_index().as_retriever(
                    similarity_top_k=similarity_top_k,
                    vector_store_query_mode="default",
                )

            nodes = retriever.retrieve(query)
            print(f'retrieved {len(nodes) if nodes else 0} source nodes')
            return [Retrieved(self.source_from_node(node, i), node) for i, node in enumerate(nodes, 1)]

    @staticmethod
    def context(sources: list[Source]) -> str:
        return "\n\n".join(f"Source [{source.id}]\n{source.text}" for source in sources)
