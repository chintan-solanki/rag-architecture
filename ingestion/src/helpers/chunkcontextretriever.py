
from pathlib import Path
import sys

SRC_DIR = Path(__file__).resolve().parent.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from models.ingestion import IndexChunk, IndexDocument
from common.models.ingestionconfig import ChunkHeaderType

class ChunkMetadataSummaryGenerator:

    def __init__(self, file_metadata):
        self.file_metadata = file_metadata | {}

    def get_summary(self, chunk:IndexChunk, section_metadata: dict):

        document_title = self.file_metadata.get('file_title', None)
        document_name = self.file_metadata.get('file_name', None)  

        header = ''
        if document_name:
            header += f'Document name: {document_name}\n'      
        if document_title:
            header += f'Document title: {document_title}\n'

        if section_metadata:
            section_title = section_metadata.get('section_title', None)
            if section_title:
                header += f'Section title: {section_title}\n'

        return header



class ChunkContextRetriever:

    def __init__(self, chunk_header_type, file_metadata):

        print(f'ChunkContextRetriever initialized with chunk_header_type: {chunk_header_type}')
        self.chunk_header_type = chunk_header_type

        # if self.chunk_header_type == ChunkHeaderType.contextualized_summary:
        #     self.summary_generator = ChunkContextualizedSummaryGenerator(chunk_header_type)
        # else:
        self.summary_generator = ChunkMetadataSummaryGenerator(file_metadata)


    def get_chunk_context(self, chunk:IndexChunk, section_metadata: dict):
        chunk_summary = self.summary_generator.get_summary(chunk, section_metadata) 
        ret = f'<context>{chunk_summary}</context>'
        return ret