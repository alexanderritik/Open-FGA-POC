from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import SLUG_PATTERN

ParentType = Literal["project", "zone"]


class ZoneCreate(BaseModel):
    id: str = Field(pattern=SLUG_PATTERN, max_length=255, examples=["north"])
    parent_type: ParentType
    parent_id: str = Field(pattern=SLUG_PATTERN, max_length=255, examples=["indian-railway"])


class ZoneRead(BaseModel):
    id: str
    parent_type: ParentType
    parent_id: str


class ZoneChildren(BaseModel):
    zone_id: str
    child_zones: list[str]
    child_structures: list[str]
