from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import SLUG_PATTERN


class ProjectCreate(BaseModel):
    id: str = Field(pattern=SLUG_PATTERN, max_length=255, examples=["indian-railway"])
    client_id: str = Field(pattern=SLUG_PATTERN, max_length=255, examples=["govt-of-india"])
    name: str = Field(min_length=1, max_length=255, examples=["Indian Railway"])


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    client_id: str
    name: str
    created_at: datetime
