from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass
from typing import Callable
from datetime import datetime


@dataclass
class IndexChunk:
    chunk_id: str
    text: str

    start_char_idx: int = 0 #start index of chunk in the original pdf file character stream
    end_char_idx: int = 0 #end index of chunk in the original pdf file character stream
    start_page_idx: int = 0 #pdf page number index where the chunk starts
    end_page_idx: int = 0 #pdf page number index where the chunk ends

@dataclass
class IndexDocument:
    doc_id: str
    text:str
    metadata: any = None

'''
Returns chunk object for a given llamaindex chunk
'''

from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.schema import Document, NodeRelationship
from llama_index.core.node_parser import SentenceSplitter

from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.vector_stores import SimpleVectorStore
from llama_index.embeddings.fastembed import FastEmbedEmbedding

import qdrant_client
from qdrant_client.http import models


class Indexer:

    def __init__(self, qdrant_url, collection_name, fast_embedding_name):

        self._collection_name = collection_name

        #initialize local embedding model
        self.local_embed = FastEmbedEmbedding(model_name=fast_embedding_name)
        
        # Initialize the Qdrant client
        self.client = qdrant_client.QdrantClient(url=qdrant_url)

        #initiaalize qdrant vector store
        
        self.vector_store = QdrantVectorStore(client=self.client, collection_name=self._collection_name)

        #initialize storage_context over the vector storage
        self.storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
            
    def _get_chunk(self, node):
        return IndexChunk(
            text = node.text,
            chunk_id = node.metadata['chunk_id']
        )

    def _update_node_metadata(self, node, chunk):

        node.metadata = {
            **node.metadata,
            
            'chunk_start_char_idx': chunk.start_char_idx,
            'chunk_end_char_idx': chunk.end_char_idx,
            'chunk_start_page_idx': chunk.start_page_idx,
            'chunk_end_page_idx': chunk.end_page_idx,
            }

    #returns ony those nodes which do not already exist in the qdrant
    def _get_new_nodes(self, nodes):

        node_ids_to_check = [node.metadata['chunk_id'] for node in nodes]

        scroll_results, _ = self.client.scroll(
            collection_name=self._collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="chunk_id", 
                        match=models.MatchAny(any=node_ids_to_check),
                    )
                ]
            ),
            with_vectors=False,
            with_payload=True, # We need the payload to read the custom string ID
            limit=len(node_ids_to_check),
        )

        # 3. Extract the found IDs from the payload
        existing_ids = {point.payload["chunk_id"] for point in scroll_results if "chunk_id" in point.payload}

        new_nodes = [node for node in nodes if node.metadata['chunk_id'] not in existing_ids]
        return new_nodes

    def index(self, 
              index_docs: list[IndexDocument], 
              transform_chunk_fn: Callable[[IndexChunk, dict], IndexChunk] = lambda chunk, metadata: chunk,
              *, 
              excluded_embed_keys: list[str] = [], 
              excluded_llm_keys: list[str] = []):

        
        splitter = SentenceSplitter(
            chunk_size=1024,
            chunk_overlap=128,
        )

        nodes = []

        print(f'splitting start: {datetime.now()}')

        for doc in index_docs:

            #create lama_doc
            llama_doc = Document(
                text=doc.text,
                metadata=asdict(doc.metadata) if doc.metadata else {},
                excluded_embed_metadata_keys=excluded_embed_keys, 
                excluded_llm_metadata_keys=excluded_llm_keys
            ) 

            #get nodes from the doc
            doc_nodes = splitter.get_nodes_from_documents([llama_doc])

            #set chunk_id for each node
            for idx, node in enumerate(doc_nodes):
                node.metadata['chunk_id'] = f'{doc.doc_id}_chunk_{idx}'

            nodes.extend(doc_nodes)

        print(f'splitting end: {datetime.now()}')

        print(f'{len(nodes)} nodes created by splitter')

        #get new nodes which do not already exist in the store
        nodes = self._get_new_nodes(nodes)    
        print(f'{len(nodes)} new node to be indexed')


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

