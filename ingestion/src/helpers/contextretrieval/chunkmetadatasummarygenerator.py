from models.ingestion import IndexChunk, IndexDocument
from .chunkcontextheader import ChunkContextHeader

class ChunkMetadataSummaryGenerator:

    '''
    Generates file metadata summary for the chunk header.
    '''

    def __init__(self, file_metadata):
        self.file_metadata = file_metadata | {}

    def get_context_header(self, chunk:IndexChunk, document: IndexDocument, comment: str) -> ChunkContextHeader:

        header = ChunkContextHeader()
        header.file_name = self.file_metadata.get('file_name', None)  
        header.file_title = self.file_metadata.get('file_title', None)
        header.comment = comment
        
        metadata = document.metadata
        if isinstance(metadata, dict):
            header.section_title = metadata.get('section_title', None)

        return header

