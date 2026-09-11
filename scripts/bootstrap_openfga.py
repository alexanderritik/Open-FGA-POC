"""Creates (or reuses) an OpenFGA store and writes the ReBAC authorization
model for this project, then prints the resulting FGA_STORE_ID and
FGA_MODEL_ID to put into .env.

This is idempotent for the store (matches by name) but always writes a new
authorization model version, since OpenFGA authorization models are
immutable once created.

Usage:
    python scripts/bootstrap_openfga.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.models.create_store_request import CreateStoreRequest
from openfga_sdk.models.metadata import Metadata
from openfga_sdk.models.object_relation import ObjectRelation
from openfga_sdk.models.relation_metadata import RelationMetadata
from openfga_sdk.models.relation_reference import RelationReference
from openfga_sdk.models.tuple_to_userset import TupleToUserset
from openfga_sdk.models.type_definition import TypeDefinition
from openfga_sdk.models.userset import Userset
from openfga_sdk.models.usersets import Usersets
from openfga_sdk.models.write_authorization_model_request import (
    WriteAuthorizationModelRequest,
)
from openfga_sdk.sync.client.client import OpenFgaClient

from app.core.config import get_settings

STORE_NAME = "openfga-rebac-poc"


def _viewer_or_inherited_from_parent() -> Userset:
    """`define viewer: [user] or viewer from parent`"""
    return Userset(
        union=Usersets(
            child=[
                Userset(this={}),
                Userset(
                    tuple_to_userset=TupleToUserset(
                        tupleset=ObjectRelation(object="", relation="parent"),
                        computed_userset=ObjectRelation(object="", relation="viewer"),
                    )
                ),
            ]
        )
    )


def build_type_definitions() -> list[TypeDefinition]:
    return [
        TypeDefinition(type="user"),
        TypeDefinition(
            type="client",
            relations={"viewer": Userset(this={})},
            metadata=Metadata(
                relations={
                    "viewer": RelationMetadata(directly_related_user_types=[RelationReference(type="user")]),
                }
            ),
        ),
        TypeDefinition(
            type="project",
            relations={
                "parent": Userset(this={}),
                "viewer": _viewer_or_inherited_from_parent(),
            },
            metadata=Metadata(
                relations={
                    "parent": RelationMetadata(directly_related_user_types=[RelationReference(type="client")]),
                    "viewer": RelationMetadata(directly_related_user_types=[RelationReference(type="user")]),
                }
            ),
        ),
        TypeDefinition(
            type="zone",
            relations={
                "parent": Userset(this={}),
                "viewer": _viewer_or_inherited_from_parent(),
            },
            metadata=Metadata(
                relations={
                    "parent": RelationMetadata(
                        directly_related_user_types=[
                            RelationReference(type="project"),
                            RelationReference(type="zone"),
                        ]
                    ),
                    "viewer": RelationMetadata(directly_related_user_types=[RelationReference(type="user")]),
                }
            ),
        ),
        TypeDefinition(
            type="structure",
            relations={
                "parent": Userset(this={}),
                "viewer": _viewer_or_inherited_from_parent(),
            },
            metadata=Metadata(
                relations={
                    "parent": RelationMetadata(
                        directly_related_user_types=[
                            RelationReference(type="project"),
                            RelationReference(type="zone"),
                        ]
                    ),
                    "viewer": RelationMetadata(directly_related_user_types=[RelationReference(type="user")]),
                }
            ),
        ),
    ]


def main() -> None:
    settings = get_settings()
    configuration = ClientConfiguration(api_url=settings.fga_api_url)

    with OpenFgaClient(configuration) as client:
        store_id = settings.fga_store_id or _find_or_create_store(client)
        client.set_store_id(store_id)

        response = client.write_authorization_model(
            WriteAuthorizationModelRequest(
                schema_version="1.1",
                type_definitions=build_type_definitions(),
            )
        )
        model_id = response.authorization_model_id

    print(f"FGA_STORE_ID={store_id}")
    print(f"FGA_MODEL_ID={model_id}")


def _find_or_create_store(client: OpenFgaClient) -> str:
    existing = client.list_stores()
    for store in existing.stores or []:
        if store.name == STORE_NAME:
            return store.id

    created = client.create_store(CreateStoreRequest(name=STORE_NAME))
    return created.id


if __name__ == "__main__":
    main()
