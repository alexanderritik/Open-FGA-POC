from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import SLUG_PATTERN


class ClientCreate(BaseModel):
    id: str = Field(
        pattern=SLUG_PATTERN,
        max_length=255,
        description="Slug-style unique identifier, e.g. 'govt-of-india'. Lowercase letters, digits, hyphens.",
        examples=["govt-of-india"],
    )
    name: str = Field(min_length=1, max_length=255, examples=["Govt of India"])


class ClientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime
