from pydantic import BaseModel, Field
from enum import Enum

class DocumentAccepted(BaseModel):
    ingestion_id: str = Field(min_length=1)

    