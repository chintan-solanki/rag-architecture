from pydantic import BaseModel, Field


class DocumentAccepted(BaseModel):
    ingestion_id: str = Field(min_length=1)
