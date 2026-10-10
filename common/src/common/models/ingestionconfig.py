from pydantic import BaseModel, Field
from enum import Enum

class ChunkHeaderType(str, Enum):
    metadata = "metadata"
    contextualized_summary = "contextualized_summary"

class IngestionConfig(BaseModel):
    chunk_header_type: ChunkHeaderType = Field(default=ChunkHeaderType.metadata)
    custom_chunk_header: str | None = Field(default=None, description="Custom chunk header to be used for all chunks. If provided, this will override the chunk_header_type setting.")
    