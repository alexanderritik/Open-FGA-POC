from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Identifiers become OpenFGA object ids (`client:<id>`) once authorization
# relationships are introduced, so they're restricted to a safe slug shape
# now rather than loosened and re-tightened later.
_ID_PATTERN = r"^[a-z0-9][a-z0-9-]{0,254}$"


class ClientCreate(BaseModel):
    id: str = Field(
        pattern=_ID_PATTERN,
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
