from typing import Literal

from pydantic import BaseModel, Field

ParentType = Literal["project", "zone"]

# Same slug shape as other OpenFGA-backed identifiers (app/schemas/client.py):
# these become `zone:<id>` object ids in OpenFGA tuples.
_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,254}$"


class ZoneCreate(BaseModel):
    id: str = Field(pattern=_ID_PATTERN, max_length=255, examples=["north"])
    parent_type: ParentType
    parent_id: str = Field(pattern=_ID_PATTERN, max_length=255, examples=["indian-railway"])


class ZoneRead(BaseModel):
    id: str
    parent_type: ParentType
    parent_id: str


class ZoneChildren(BaseModel):
    zone_id: str
    child_zones: list[str]
    child_structures: list[str]
