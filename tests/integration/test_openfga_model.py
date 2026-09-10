"""Verifies the core ReBAC behaviors of the OpenFGA authorization model
against a live OpenFGA instance, using the hierarchy:

    client:modeltest-client
        -> project:modeltest-project
            -> zone:modeltest-north
                -> zone:modeltest-delhi
                    -> zone:modeltest-central
                        -> structure:modeltest-bridge
            -> zone:modeltest-south (sibling branch)

Object ids are prefixed "modeltest-" (not e.g. "govt-of-india") so this
test's tuples never collide with scripts/seed_demo.py's real demo data if
both happen to exist in the same OpenFGA store at once — OpenFGA rejects
writing an already-existing identical tuple, so a shared id would break
this fixture's setup.

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
    ClientTuple(user="client:modeltest-client", relation="parent", object="project:modeltest-project"),
    ClientTuple(user="project:modeltest-project", relation="parent", object="zone:modeltest-north"),
    ClientTuple(user="zone:modeltest-north", relation="parent", object="zone:modeltest-delhi"),
    ClientTuple(user="zone:modeltest-delhi", relation="parent", object="zone:modeltest-central"),
    ClientTuple(user="project:modeltest-project", relation="parent", object="zone:modeltest-south"),
    ClientTuple(user="zone:modeltest-central", relation="parent", object="structure:modeltest-bridge"),
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
    """A viewer grant at zone:modeltest-north (the topmost zone) must reach
    a structure three zone-levels below it: north -> delhi -> central ->
    structure."""
    grant = [ClientTuple(user="user:modeltest-alice", relation="viewer", object="zone:modeltest-north")]
    fga_client.write(ClientWriteRequest(writes=grant))
    try:
        assert check(fga_client, "user:modeltest-alice", "viewer", "zone:modeltest-north")
        assert check(fga_client, "user:modeltest-alice", "viewer", "zone:modeltest-delhi")
        assert check(fga_client, "user:modeltest-alice", "viewer", "zone:modeltest-central")
        assert check(fga_client, "user:modeltest-alice", "viewer", "structure:modeltest-bridge")
    finally:
        fga_client.write(ClientWriteRequest(deletes=grant))


def test_no_cross_branch_inheritance(fga_client, hierarchy):
    """A viewer grant at zone:modeltest-north must not leak to the sibling
    zone:modeltest-south."""
    grant = [ClientTuple(user="user:modeltest-alice", relation="viewer", object="zone:modeltest-north")]
    fga_client.write(ClientWriteRequest(writes=grant))
    try:
        assert not check(fga_client, "user:modeltest-alice", "viewer", "zone:modeltest-south")
    finally:
        fga_client.write(ClientWriteRequest(deletes=grant))


def test_no_upward_inheritance_from_structure(fga_client, hierarchy):
    """A viewer grant at structure:modeltest-bridge only must not reach any
    ancestor: the central/delhi/north zones, the project, or the client."""
    grant = [ClientTuple(user="user:modeltest-carlos", relation="viewer", object="structure:modeltest-bridge")]
    fga_client.write(ClientWriteRequest(writes=grant))
    try:
        assert check(fga_client, "user:modeltest-carlos", "viewer", "structure:modeltest-bridge")
        assert not check(fga_client, "user:modeltest-carlos", "viewer", "zone:modeltest-central")
        assert not check(fga_client, "user:modeltest-carlos", "viewer", "zone:modeltest-delhi")
        assert not check(fga_client, "user:modeltest-carlos", "viewer", "zone:modeltest-north")
        assert not check(fga_client, "user:modeltest-carlos", "viewer", "project:modeltest-project")
        assert not check(fga_client, "user:modeltest-carlos", "viewer", "client:modeltest-client")
    finally:
        fga_client.write(ClientWriteRequest(deletes=grant))


def test_direct_client_viewer_inherits_down_to_project(fga_client, hierarchy):
    grant = [ClientTuple(user="user:modeltest-bob", relation="viewer", object="client:modeltest-client")]
    fga_client.write(ClientWriteRequest(writes=grant))
    try:
        assert check(fga_client, "user:modeltest-bob", "viewer", "client:modeltest-client")
        assert check(fga_client, "user:modeltest-bob", "viewer", "project:modeltest-project")
        assert check(fga_client, "user:modeltest-bob", "viewer", "zone:modeltest-north")
        assert check(fga_client, "user:modeltest-bob", "viewer", "structure:modeltest-bridge")
    finally:
        fga_client.write(ClientWriteRequest(deletes=grant))


def test_no_grant_denies_access(fga_client, hierarchy):
    assert not check(fga_client, "user:modeltest-nobody", "viewer", "structure:modeltest-bridge")
    assert not check(fga_client, "user:modeltest-nobody", "viewer", "zone:modeltest-north")
