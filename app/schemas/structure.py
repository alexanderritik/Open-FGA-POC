from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import SLUG_PATTERN

# Structure's OpenFGA `parent` relation accepts [project, zone] (see
# app/authorization/model.fga) — a structure can sit directly under a
# Project (no Zone in between) or under a Zone at any nesting depth.
# Unlike Zone, Structure still cannot be parented directly to a Client.
ParentType = Literal["project", "zone"]


class StructureCreate(BaseModel):
    id: str = Field(pattern=SLUG_PATTERN, max_length=255, examples=["yamuna-bridge"])
    name: str = Field(min_length=1, max_length=255, examples=["Yamuna Bridge"])
    parent_type: ParentType
    parent_id: str = Field(pattern=SLUG_PATTERN, max_length=255, examples=["central"])


class StructureListItem(BaseModel):
    """Business data only — used for the list endpoint so it doesn't need
    one OpenFGA read per row."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime


class StructureRead(StructureListItem):
    """Business data plus the OpenFGA-recorded parent. parent_type/parent_id
    are None only if the structure's business row exists but its OpenFGA
    parent tuple does not — an inconsistent state that should not occur in
    normal operation (see app/services/structure_service.py) but is
    represented rather than hidden if it's ever observed."""

    parent_type: ParentType | None = None
    parent_id: str | None = None
