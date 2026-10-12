
from models.ingestion import IndexChunk, IndexDocument
from common.models.ingestionconfig import ChunkHeaderType
from .chunkmetadatasummarygenerator import ChunkMetadataSummaryGenerator
from .chunkcontextualizedsummarygenerator import ChunkContextualizedSummaryGenerator

from dicttoxml import dicttoxml

class ChunkContextRetriever:

    '''
    Provides chunk context based on the chunk header type. Chunk context can either come from
        1. file metadata (ChunkMetadaSummaryGenerator)
        2. contextualized chunk summary by LLM (ChunkContextualizedSummaryGenerator)
    '''

    def __init__(self, ingestion_config, file_metadata, llm_model: str):
        if ingestion_config.chunk_header_type == ChunkHeaderType.contextualized_chunk_summary:
            self.summary_generator = ChunkContextualizedSummaryGenerator(llm_model)
        else:
            self.summary_generator = ChunkMetadataSummaryGenerator(file_metadata)
        
        self.comment = ingestion_config.comment

    def get_chunk_context(self, chunk:IndexChunk, document: IndexDocument):
        context_header = self.summary_generator.get_context_header(chunk, document, self.comment)

        if self.comment and self.comment.strip():
            context_header.comment = self.comment.strip()

        header_summary = ''
        if context_header:
            header_dict = {k:v for k,v in vars(context_header).items() if v}

            xml_bytes = dicttoxml(header_dict, custom_root='ChunkContext', attr_type=False)
            header_summary = xml_bytes.decode('utf-8')

        return header_summary