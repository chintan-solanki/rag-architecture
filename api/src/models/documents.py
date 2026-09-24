from pydantic import BaseModel, Field


class DocumentAccepted(BaseModel):
    document_id: str = Field(min_length=1)
