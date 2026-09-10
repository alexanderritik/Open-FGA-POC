from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import SLUG_PATTERN, USER_ID_PATTERN

ResourceType = Literal["client", "project", "zone", "structure"]

# The authorization model (app/authorization/model.fga) currently defines a
# single relation, "viewer", on every type — kept as a Literal (rather than
# a free-form string) so an unsupported permission is a clear 422 from
# request validation instead of an opaque error from OpenFGA.
Permission = Literal["viewer"]


class CheckResponse(BaseModel):
    allowed: bool


class GrantRequest(BaseModel):
    user: str = Field(pattern=USER_ID_PATTERN, examples=["user:parth"])
    resource_type: ResourceType
    resource_id: str = Field(pattern=SLUG_PATTERN, max_length=255)
    permission: Permission = "viewer"


class GrantResponse(BaseModel):
    user: str
    resource_type: ResourceType
    resource_id: str
    permission: Permission
