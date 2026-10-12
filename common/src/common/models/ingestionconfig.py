from pydantic import BaseModel, Field
from enum import Enum

class ChunkHeaderType(str, Enum):
    file_metadata = "file_metadata"
    contextualized_chunk_summary = "contextualized_chunk_summary"

class IngestionConfig(BaseModel):
    chunk_header_type: ChunkHeaderType = Field(default=ChunkHeaderType.file_metadata)
    comment: str | None = Field(default=None, description="Optional comment about the document.")