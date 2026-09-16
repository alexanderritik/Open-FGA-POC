from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

ContainerType = Literal["client", "project", "zone"]


class StructureNode(BaseModel):
    """A structure is always a leaf: nothing in the OpenFGA model
    (app/authorization/model.fga) ever defines a `parent` relation
    pointing at a structure, so unlike ContainerNode this carries no
    `children` field rather than an always-empty list."""

    type: Literal["structure"] = "structure"
    id: str
    name: str | None = None


class ContainerNode(BaseModel):
    type: ContainerType
    id: str
    # None for zone nodes: Zone has no business data anywhere (see
    # app/db/models/structure.py and the architecture notes in README.md),
    # so a zone's only identity is its id.
    name: str | None = None
    children: list[TreeNode] = []


TreeNode = Annotated[Union[ContainerNode, StructureNode], Field(discriminator="type")]

ContainerNode.model_rebuild()
