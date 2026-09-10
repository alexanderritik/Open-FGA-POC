"""Verifies the core ReBAC behaviors of the OpenFGA authorization model
against a live OpenFGA instance, using the hierarchy:

    client:govt-of-india
        -> project:indian-railway
            -> zone:north
                -> zone:delhi
                    -> zone:central
                        -> structure:yamuna-bridge
            -> zone:south (sibling branch)

Requires the docker-compose OpenFGA stack to be running with
FGA_STORE_ID/FGA_MODEL_ID set (see scripts/bootstrap_openfga.py).
"""

import pytest
from openfga_sdk.client.configuration import ClientConfiguration
from openfga_sdk.client.models.check_request import ClientCheckRequest
from openfga_sdk.client.models.tuple import ClientTuple
from openfga_sdk.client.models.write_request import ClientWriteRequest
from openfga_sdk.sync.client.client import OpenFgaClient

from app.core.config import get_settings

HIERARCHY_TUPLES = [
    ClientTuple(user="client:govt-of-india", relation="parent", object="project:indian-railway"),
    ClientTuple(user="project:indian-railway", relation="parent", object="zone:north"),
    ClientTuple(user="zone:north", relation="parent", object="zone:delhi"),
    ClientTuple(user="zone:delhi", relation="parent", object="zone:central"),
    ClientTuple(user="project:indian-railway", relation="parent", object="zone:south"),
    ClientTuple(user="zone:central", relation="parent", object="structure:yamuna-bridge"),
]


@pytest.fixture
def fga_client():
    settings = get_settings()
    if not settings.fga_store_id or not settings.fga_model_id:
        pytest.skip("FGA_STORE_ID/FGA_MODEL_ID not configured; run scripts/bootstrap_openfga.py first")

    configuration = ClientConfiguration(
        api_url=settings.fga_api_url,
        store_id=settings.fga_store_id,
        authorization_model_id=settings.fga_model_id,
    )
    with OpenFgaClient(configuration) as client:
        yield client


def check(client: OpenFgaClient, user: str, relation: str, obj: str) -> bool:
    return bool(client.check(ClientCheckRequest(user=user, relation=relation, object=obj)).allowed)


@pytest.fixture
def hierarchy(fga_client):
    fga_client.write(ClientWriteRequest(writes=HIERARCHY_TUPLES))
    yield
    fga_client.write(ClientWriteRequest(deletes=HIERARCHY_TUPLES))


def test_recursive_zone_downward_inheritance_reaches_structure(fga_client, hierarchy):
    """A viewer grant at zone:north (the topmost zone) must reach a structure
    three zone-levels below it: zone:north -> zone:delhi -> zone:central ->
    structure:yamuna-bridge."""
    grant = [ClientTuple(user="user:alice", relation="viewer", object="zone:north")]
    fga_client.write(ClientWriteRequest(writes=grant))
    try:
        assert check(fga_client, "user:alice", "viewer", "zone:north")
        assert check(fga_client, "user:alice", "viewer", "zone:delhi")
        assert check(fga_client, "user:alice", "viewer", "zone:central")
        assert check(fga_client, "user:alice", "viewer", "structure:yamuna-bridge")
    finally:
        fga_client.write(ClientWriteRequest(deletes=grant))


def test_no_cross_branch_inheritance(fga_client, hierarchy):
    """A viewer grant at zone:north must not leak to the sibling zone:south."""
    grant = [ClientTuple(user="user:alice", relation="viewer", object="zone:north")]
    fga_client.write(ClientWriteRequest(writes=grant))
    try:
        assert not check(fga_client, "user:alice", "viewer", "zone:south")
    finally:
        fga_client.write(ClientWriteRequest(deletes=grant))


def test_no_upward_inheritance_from_structure(fga_client, hierarchy):
    """A viewer grant at structure:yamuna-bridge only must not reach any
    ancestor: zone:central, zone:delhi, zone:north, the project, or the
    client."""
    grant = [ClientTuple(user="user:carlos", relation="viewer", object="structure:yamuna-bridge")]
    fga_client.write(ClientWriteRequest(writes=grant))
    try:
        assert check(fga_client, "user:carlos", "viewer", "structure:yamuna-bridge")
        assert not check(fga_client, "user:carlos", "viewer", "zone:central")
        assert not check(fga_client, "user:carlos", "viewer", "zone:delhi")
        assert not check(fga_client, "user:carlos", "viewer", "zone:north")
        assert not check(fga_client, "user:carlos", "viewer", "project:indian-railway")
        assert not check(fga_client, "user:carlos", "viewer", "client:govt-of-india")
    finally:
        fga_client.write(ClientWriteRequest(deletes=grant))


def test_direct_client_viewer_inherits_down_to_project(fga_client, hierarchy):
    grant = [ClientTuple(user="user:bob", relation="viewer", object="client:govt-of-india")]
    fga_client.write(ClientWriteRequest(writes=grant))
    try:
        assert check(fga_client, "user:bob", "viewer", "client:govt-of-india")
        assert check(fga_client, "user:bob", "viewer", "project:indian-railway")
        assert check(fga_client, "user:bob", "viewer", "zone:north")
        assert check(fga_client, "user:bob", "viewer", "structure:yamuna-bridge")
    finally:
        fga_client.write(ClientWriteRequest(deletes=grant))


def test_no_grant_denies_access(fga_client, hierarchy):
    assert not check(fga_client, "user:nobody", "viewer", "structure:yamuna-bridge")
    assert not check(fga_client, "user:nobody", "viewer", "zone:north")
