from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class SearchType(str, Enum):
    dense = "dense"
    bm25 = "bm25"
    hybrid = "hybrid"


class SearchConfig(BaseModel):
    top_k: int | None = Field(default=None, ge=1, le=100)


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    search_type: SearchType = SearchType.hybrid
    search: SearchConfig = Field(default_factory=SearchConfig)


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
    section_title: str | None = None
    file_name: str | None = None
    file_title: str | None = None
    file_author: str | None = None
    chunk_start_page_idx: int | None = None
    chunk_end_page_idx: int | None = None


class QueryResponse(BaseModel):
    answer: list[AnswerPart] = Field(default_factory=list)
    sources: list[Source] = Field(default_factory=list)
