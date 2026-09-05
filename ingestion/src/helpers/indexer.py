from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass
from typing import Callable


@dataclass
class IndexChunk:
    text: str

    chunk_id: str = ''
    start_char_idx: int = 0 #start index of chunk in the original pdf file character stream
    end_char_idx: int = 0 #end index of chunk in the original pdf file character stream
    start_page_idx: int = 0 #pdf page number index where the chunk starts
    end_page_idx: int = 0 #pdf page number index where the chunk ends

@dataclass
class IndexDocument:
    text:str
    metadata: any = None

'''
Returns chunk object for a given llamaindex chunk
'''

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.llms.openai import OpenAI
from llama_index.core.schema import Document, NodeRelationship
from llama_index.core.node_parser import SentenceSplitter

from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.vector_stores import SimpleVectorStore
from llama_index.embeddings.fastembed import FastEmbedEmbedding

import qdrant_client


class Indexer:

    def __init__(self):

        #initialize local embedding model
        self.local_embed = FastEmbedEmbedding(model_name="BAAI/bge-small-en-v1.5")
        #self.local_embed = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        
        # Initialize the Qdrant client
        self.client = qdrant_client.QdrantClient(url="http://qdrant:6333")

        #initiaalize qdrant vector store
        
        self.vector_store = QdrantVectorStore(client=self.client, collection_name="test_collection")
        #self.vector_store = SimpleVectorStore()

        #initialize storage_context over the vector storage
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
            
    def _get_chunk(self, node):
        return IndexChunk(
            text = node.text,
            chunk_id = node.id_
        )

    def _update_node_metadata(self, node, chunk):

        node.metadata = {
            **node.metadata,
            'chunk_id': node.id_,
            'chunk_start_char_idx': chunk.start_char_idx,
            'chunk_end_char_idx': chunk.end_char_idx,
            'chunk_start_page_idx': chunk.start_page_idx,
            'chunk_end_page_idx': chunk.end_page_idx,
            }


    def index(self, 
              index_docs: list[IndexDocument], 
              transform_chunk_fn: Callable[[IndexChunk, dict], IndexChunk] = lambda chunk, metadata: chunk,
              *, 
              excluded_embed_keys: list[str] = [], 
              excluded_llm_keys: list[str] = []):

        #create llama index documents from the index_docs
        llama_docs = [Document(
            text=doc.text,
            metadata=asdict(doc.metadata) if doc.metadata else {},
            excluded_embed_metadata_keys=excluded_embed_keys, 
            excluded_llm_metadata_keys=excluded_llm_keys
        ) for doc in index_docs]

        #create llamaindex nodes 
        splitter = SentenceSplitter(
            chunk_size=1024,
            chunk_overlap=128,
        )
        nodes = splitter.get_nodes_from_documents(llama_docs)

        #build Indexchunk objects from llamaindex nodes 
        chunks = []
        for node in nodes:
            chunk = self._get_chunk(node)

            #run the app call back to transform the chunk with as per app logic (e.g. adding citation data to the chunk)
            doc_metadata = node.relationships[NodeRelationship.SOURCE].metadata
            chunk = transform_chunk_fn(chunk, doc_metadata)

            #update the node metadata with chunk citation data.
            self._update_node_metadata(node, chunk)
            chunks.append(chunk)

        #build index over nodes
        index = VectorStoreIndex(
            nodes, 
            embed_model=self.local_embed, 
            storage_context=self.storage_context
            )

        return index

