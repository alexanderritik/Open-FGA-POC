from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

NodeType = Literal["client", "project", "zone", "structure"]


class TreeNode(BaseModel):
    type: NodeType
    id: str
    # None for zone nodes: Zone has no business data anywhere (see
    # app/db/models/structure.py and the architecture notes in README.md),
    # so a zone's only identity is its id.
    name: str | None = None
    children: list[TreeNode] = []


TreeNode.model_rebuild()
