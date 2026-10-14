from enum import Enum
from pydantic import BaseModel, ConfigDict, Field


class RetrievalType(str, Enum):
    dense = "dense"
    bm25 = "bm25"
    hybrid = "hybrid"

class RetrievalConfig(BaseModel):
    retrieval_type: RetrievalType | None = None
    use_reranker: bool | None = None
    top_k: int | None = Field(default=None, ge=1, le=10)
    candidate_pool_size: int | None = Field(default=None, ge=1, le=100)
    reranker_score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    alpha: float | None = Field(default=None, ge=0.0, le=1.0)

class GenerationConfig(BaseModel):
    temperature: float | None = Field(default=0.7, ge=0.0, le=1.0)
    max_output_tokens: int | None = Field(default=512, ge=1, le=2048)
    top_p: float | None = Field(default=0.9, ge=0.0, le=1.0)

class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    retrieval_config: RetrievalConfig = Field(default_factory=RetrievalConfig)
    generation_config: GenerationConfig = Field(default_factory=GenerationConfig)

class Citation(BaseModel):
    source_id: int = Field(ge=1)

class AnswerPart(BaseModel):
    text: str
    citations: list[Citation] = Field(default_factory=list)


class Source(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: int = Field(ge=1)
    chunk_id: str | None = None
    document_id: str | None = None
    text: str
    relevance_score: float | None = Field(default=None, ge=0.0, le=1.0)
    section_title: str | None = None
    file_name: str | None = None
    original_file_name: str | None = None
    file_title: str | None = None
    file_author: str | None = None
    chunk_start_page_idx: int | None = None
    chunk_end_page_idx: int | None = None


class QueryResponse(BaseModel):
    answer: list[AnswerPart] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
